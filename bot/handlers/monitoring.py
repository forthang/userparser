import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupCRUD, KeywordCRUD, CityCRUD, OrderCRUD
from bot.keyboards.main_menu import MainMenuText, get_main_menu
from bot.keyboards.inline import get_order_keyboard, get_order_taken_keyboard
from bot.services.userbot import UserBotService, UserBotManager
from bot.services.parser import MessageParser
from bot.config import config
from userbot.client import userbot_pool

logger = logging.getLogger(__name__)

router = Router()

active_monitors = {}

# Глобальная ссылка на бот для callback
_bot_instance: Bot = None


def set_bot_instance(bot: Bot):
    """Установить инстанс бота для использования в callback"""
    global _bot_instance
    _bot_instance = bot


@router.message(F.text == MainMenuText.MONITORING_ON)
async def monitoring_start(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        if not user.session_string:
            await message.answer(
                "⚠️ Сначала авторизуйте ваш аккаунт.\n"
                "Нажмите /start для начала."
            )
            return

        if not user.is_subscription_active:
            await message.answer(
                "⚠️ У вас нет активной подписки.\n"
                "Оформите подписку, чтобы использовать мониторинг."
            )
            return

        enabled_groups = await GroupCRUD.get_enabled_groups(session, user.id)
        if not enabled_groups:
            await message.answer(
                "⚠️ Вы не выбрали группы для мониторинга.\n"
                "Перейдите в раздел «Список групп» и выберите группы."
            )
            return

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)
        if not keywords:
            await message.answer(
                "⚠️ У вас нет ключевых слов для поиска.\n"
                "Добавьте слова в разделе «Ключевые слова»."
            )
            return

        await UserCRUD.toggle_monitoring(session, user.id, True)

        # Запускаем userbot клиент для мониторинга
        if _bot_instance and not userbot_pool.is_running(user.id):
            async def message_callback(
                user_tg_id: int,
                group_id: int,
                group_name: str,
                msg_id: int,
                msg_text: str,
            ):
                await process_group_message(
                    bot=_bot_instance,
                    user_telegram_id=user_tg_id,
                    group_id=group_id,
                    group_name=group_name,
                    message_id=msg_id,
                    message_text=msg_text,
                )

            success = await userbot_pool.start_client(
                user_db_id=user.id,
                user_telegram_id=user.telegram_id,
                session_string=user.session_string,
                on_message_callback=message_callback,
            )

            if not success:
                await UserCRUD.toggle_monitoring(session, user.id, False)
                await message.answer(
                    "❌ Не удалось запустить мониторинг.\n"
                    "Попробуйте переавторизоваться или обратитесь в поддержку."
                )
                return

            logger.info(f"Started userbot for user {user.telegram_id} via monitoring button")

        await message.answer(
            f"✅ <b>Мониторинг запущен!</b>\n\n"
            f"📋 Отслеживаемых групп: {len(enabled_groups)}\n"
            f"🔤 Ключевых слов: {len(keywords)}\n\n"
            f"Бот будет присылать уведомления о новых заказах.",
            parse_mode="HTML",
            reply_markup=get_main_menu(monitoring_enabled=True),
        )


@router.message(F.text == MainMenuText.MONITORING_OFF)
async def monitoring_stop(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        await UserCRUD.toggle_monitoring(session, user.id, False)

        if user.id in active_monitors:
            del active_monitors[user.id]

        # Останавливаем userbot клиент
        await userbot_pool.stop_client(user.id)
        logger.info(f"Stopped userbot for user {user.telegram_id}")

        await message.answer(
            "⏹ <b>Мониторинг остановлен</b>\n\n"
            "Вы больше не будете получать уведомления о заказах.",
            parse_mode="HTML",
            reply_markup=get_main_menu(monitoring_enabled=False),
        )


@router.callback_query(F.data == "monitoring_start")
async def monitoring_start_callback(callback: CallbackQuery):
    await callback.answer()

    fake_message = callback.message
    fake_message.from_user = callback.from_user
    fake_message.text = MainMenuText.MONITORING_ON

    await monitoring_start(fake_message)


@router.callback_query(F.data == "monitoring_stop")
async def monitoring_stop_callback(callback: CallbackQuery):
    await callback.answer()

    fake_message = callback.message
    fake_message.from_user = callback.from_user
    fake_message.text = MainMenuText.MONITORING_OFF

    await monitoring_stop(fake_message)


@router.callback_query(F.data.startswith("order_take:"))
async def order_take(callback: CallbackQuery):
    """Обработка взятия заказа - отправляет ответ в группу и перекидывает туда пользователя"""
    order_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user or not user.session_string:
            await callback.answer("Ошибка: аккаунт не подключен", show_alert=True)
            return

        order = await OrderCRUD.get_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if order.responded:
            await callback.answer("Вы уже взяли этот заказ", show_alert=True)
            return

        await callback.answer("⏳ Отправляю отклик...")

        try:
            # Получаем текст отклика пользователя или дефолтный
            response_text = user.response_text or config.response_text

            # Используем работающий клиент из пула если есть
            if userbot_pool.is_running(user.id):
                client = userbot_pool._clients[user.id].client
                await client.send_message(
                    chat_id=order.telegram_group_id,
                    text=response_text,
                    reply_to_message_id=order.message_id,
                )
                logger.info(f"Sent reply via pool client to {order.telegram_group_id}")
            else:
                # Если клиент не запущен, создаём временный
                userbot = UserBotService(
                    api_id=config.telegram_api.api_id,
                    api_hash=config.telegram_api.api_hash,
                    session_string=user.session_string,
                )
                await userbot.send_reply(
                    chat_id=order.telegram_group_id,
                    message_id=order.message_id,
                    text=response_text,
                )

            await OrderCRUD.mark_responded(session, order_id)

            # Обновляем клавиатуру - теперь показываем что заказ взят
            await callback.message.edit_reply_markup(
                reply_markup=get_order_taken_keyboard(order.telegram_group_id, order.message_id),
            )

            await callback.message.answer(
                "✅ Отклик отправлен!\n\n"
                "Нажмите кнопку «Перейти в группу» чтобы продолжить общение."
            )

        except Exception as e:
            logger.error(f"Error taking order: {e}")
            await callback.message.answer(
                f"❌ Ошибка при отправке отклика: {str(e)}\n"
                "Попробуйте ещё раз или напишите вручную."
            )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


async def process_group_message(
    bot: Bot,
    user_telegram_id: int,
    group_id: int,
    group_name: str,
    message_id: int,
    message_text: str,
):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, user_telegram_id)

        if not user or not user.monitoring_enabled:
            return

        if not user.is_subscription_active:
            return

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)
        cities = await CityCRUD.get_user_cities(session, user.id)

        parser = MessageParser(keywords, cities)
        is_order, found_keyword, found_city = parser.check_message(message_text)

        if not is_order:
            return

        db_groups = await GroupCRUD.get_enabled_groups(session, user.id)
        db_group = next((g for g in db_groups if g.telegram_group_id == group_id), None)

        if not db_group:
            return

        order = await OrderCRUD.create_order(
            session,
            user_id=user.id,
            group_id=db_group.id,
            telegram_group_id=group_id,
            message_id=message_id,
            message_text=message_text,
        )

        notification = parser.format_notification(
            message_text=message_text,
            group_name=group_name,
            keyword=found_keyword,
            city=found_city,
        )

        try:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=notification,
                parse_mode="HTML",
                reply_markup=get_order_keyboard(order.id, group_id, message_id),
            )
        except Exception as e:
            logger.error(f"Error sending notification to user {user_telegram_id}: {e}")
