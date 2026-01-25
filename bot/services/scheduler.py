import asyncio
import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupMessageCRUD
from bot.config import config

logger = logging.getLogger(__name__)


class SubscriptionScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Subscription scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
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

    async def _cleanup_old_messages(self):
        """Cleanup group messages older than 24 hours"""
        try:
            async with async_session() as session:
                deleted = await GroupMessageCRUD.cleanup_old_messages(session)
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old group messages")
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
