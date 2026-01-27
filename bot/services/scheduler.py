import asyncio
import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupMessageCRUD, PaymentCRUD, BotSettingsCRUD, SharedGroupMessageCRUD, OrderDeliveryCRUD
from bot.services.payment import PaymentService, PaymentSystem, payment_manager
from bot.keyboards.main_menu import get_main_menu
from bot.config import config

logger = logging.getLogger(__name__)


class SubscriptionScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._task: Optional[asyncio.Task] = None
        self._payment_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        self._payment_task = asyncio.create_task(self._run_payment_checker())
        logger.info("Subscription scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._payment_task:
            self._payment_task.cancel()
            try:
                await self._payment_task
            except asyncio.CancelledError:
                pass
        logger.info("Subscription scheduler stopped")

    async def _run(self):
        while self._running:
            try:
                await self._check_subscriptions()
                await self._cleanup_old_messages()
            except Exception as e:
                logger.error(f"Error in subscription scheduler: {e}")

            await asyncio.sleep(3600)

    async def _run_payment_checker(self):
        """Проверяет pending платежи каждые 15 секунд"""
        while self._running:
            try:
                await self._check_pending_payments()
            except Exception as e:
                logger.error(f"Error checking payments: {e}")

            await asyncio.sleep(15)

    async def _check_pending_payments(self):
        """Проверяет все ожидающие платежи и активирует подписки"""
        if not payment_manager.pending_payments:
            return

        # Копируем чтобы избежать изменения во время итерации
        pending_copy = dict(payment_manager.pending_payments)

        for user_id, payment_info in pending_copy.items():
            try:
                payment_id = payment_info["payment_id"]
                system = payment_info["system"]

                # Проверяем статус
                payment_data = await PaymentService.check_payment(
                    system=system,
                    payment_id=payment_id,
                )

                if not payment_data:
                    continue

                if PaymentService.is_payment_successful(system, payment_data.get("status", "")):
                    # Оплата прошла - активируем подписку
                    async with async_session() as session:
                        # Получаем настройки
                        days_str = await BotSettingsCRUD.get(session, "subscription_days", str(config.subscription.days))
                        days = int(days_str)

                        # Получаем пользователя по внутреннему ID
                        from sqlalchemy import select
                        from bot.database.models import User
                        result = await session.execute(select(User).where(User.id == user_id))
                        user = result.scalar_one_or_none()

                        if user:
                            # Активируем подписку
                            await UserCRUD.update_subscription(session, user.id, days)

                            # Подтверждаем платеж в БД
                            await PaymentCRUD.confirm_payment(session, payment_id)

                            # Удаляем из pending
                            payment_manager.remove_pending(user_id)

                            # Уведомляем пользователя
                            try:
                                await self.bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=(
                                        f"✅ <b>Оплата прошла успешно!</b>\n\n"
                                        f"Ваша подписка активирована на {days} дней.\n"
                                        f"Теперь вы можете использовать все функции бота."
                                    ),
                                    parse_mode="HTML",
                                    reply_markup=get_main_menu(user.monitoring_enabled),
                                )
                                logger.info(f"Auto-confirmed payment for user {user.telegram_id}")
                            except Exception as e:
                                logger.error(f"Error notifying user {user.telegram_id}: {e}")

            except Exception as e:
                logger.error(f"Error processing payment for user {user_id}: {e}")

    async def _cleanup_old_messages(self):
        """Cleanup group messages older than 24 hours"""
        try:
            async with async_session() as session:
                # Cleanup per-user group messages
                deleted = await GroupMessageCRUD.cleanup_old_messages(session)
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old group messages")

                # Cleanup order deliveries first (references shared messages)
                deleted_deliveries = await OrderDeliveryCRUD.cleanup_old(session)
                if deleted_deliveries > 0:
                    logger.info(f"Cleaned up {deleted_deliveries} old order deliveries")

                # Cleanup shared pool messages
                deleted_shared = await SharedGroupMessageCRUD.cleanup_old(session)
                if deleted_shared > 0:
                    logger.info(f"Cleaned up {deleted_shared} old shared pool messages")
        except Exception as e:
            logger.error(f"Error cleaning up old messages: {e}")

    async def _check_subscriptions(self):
        logger.info("Checking subscriptions...")

        async with async_session() as session:
            expiring_users = await UserCRUD.get_expiring_subscriptions(
                session, days_before=3
            )

            for user in expiring_users:
                try:
                    days_left = (user.subscription_end - datetime.utcnow()).days

                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"⚠️ <b>Внимание!</b>\n\n"
                            f"Ваша подписка заканчивается через {days_left} дн.\n"
                            f"({user.subscription_end.strftime('%d.%m.%Y')})\n\n"
                            f"Продлите подписку, чтобы продолжить использовать мониторинг.\n"
                            f"Нажмите: 💳 Подписка → Продлить"
                        ),
                        parse_mode="HTML",
                    )
                    logger.info(f"Sent expiration reminder to user {user.telegram_id}")

                except Exception as e:
                    logger.error(
                        f"Error sending reminder to user {user.telegram_id}: {e}"
                    )

            expired_users = await UserCRUD.deactivate_expired(session)

            for user in expired_users:
                try:
                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            "❌ <b>Подписка истекла</b>\n\n"
                            "Ваша подписка закончилась.\n"
                            "Мониторинг остановлен, сессия удалена.\n\n"
                            "Для продолжения работы оформите новую подписку\n"
                            "и авторизуйте аккаунт заново."
                        ),
                        parse_mode="HTML",
                    )
                    logger.info(f"Deactivated user {user.telegram_id}")

                except Exception as e:
                    logger.error(
                        f"Error notifying deactivated user {user.telegram_id}: {e}"
                    )

        logger.info(
            f"Subscription check complete. "
            f"Reminders sent: {len(expiring_users)}, "
            f"Deactivated: {len(expired_users)}"
        )


scheduler: Optional[SubscriptionScheduler] = None


def get_scheduler(bot: Bot) -> SubscriptionScheduler:
    global scheduler
    if scheduler is None:
        scheduler = SubscriptionScheduler(bot)
    return scheduler
