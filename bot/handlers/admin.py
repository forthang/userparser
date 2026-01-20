import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from bot.database.connection import async_session
from bot.database.models import User, Group, Order, Payment
from bot.database.crud import UserCRUD
from bot.config import config

logger = logging.getLogger(__name__)

router = Router()


class AdminStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_user_id_for_ban = State()
    waiting_user_id_for_unban = State()
    waiting_user_id_for_admin = State()
    waiting_user_id_for_remove_admin = State()


async def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    # Проверяем в конфиге (суперадмины)
    if user_id in config.bot.admin_ids:
        return True
    # Проверяем в БД
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, user_id)
        return user and user.is_admin


def get_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban"),
        InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban"),
    )
    builder.row(
        InlineKeyboardButton(text="👑 Назначить админа", callback_data="admin_add_admin"),
        InlineKeyboardButton(text="👤 Снять админа", callback_data="admin_remove_admin"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список админов", callback_data="admin_list_admins"),
    )
    return builder.as_markup()


def get_back_to_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_menu"),
    )
    return builder.as_markup()


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    """Админ-панель"""
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    await state.clear()
    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


# === СТАТИСТИКА ===

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("Загружаю статистику...")

    async with async_session() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        active_users = await session.scalar(
            select(func.count(User.id)).where(User.subscription_end > datetime.utcnow())
        )
        monitoring_users = await session.scalar(
            select(func.count(User.id)).where(User.monitoring_enabled == True)
        )
        authorized_users = await session.scalar(
            select(func.count(User.id)).where(User.session_string.isnot(None))
        )
        banned_users = await session.scalar(
            select(func.count(User.id)).where(User.is_banned == True)
        )

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = await session.scalar(
            select(func.count(User.id)).where(User.created_at >= today_start)
        )

        week_ago = datetime.utcnow() - timedelta(days=7)
        new_week = await session.scalar(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )

        total_groups = await session.scalar(select(func.count(Group.id)))
        enabled_groups = await session.scalar(
            select(func.count(Group.id)).where(Group.is_enabled == True)
        )

        total_orders = await session.scalar(select(func.count(Order.id)))
        orders_today = await session.scalar(
            select(func.count(Order.id)).where(Order.created_at >= today_start)
        )
        responded_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.responded == True)
        )

        confirmed_payments = await session.scalar(
            select(func.count(Payment.id)).where(Payment.status == "confirmed")
        )
        total_revenue = await session.scalar(
            select(func.sum(Payment.amount)).where(Payment.status == "confirmed")
        ) or 0

        text = (
            "📊 <b>Статистика бота</b>\n\n"
            "<b>👥 Пользователи:</b>\n"
            f"├ Всего: {total_users}\n"
            f"├ Авторизованных: {authorized_users}\n"
            f"├ С подпиской: {active_users}\n"
            f"├ Мониторинг: {monitoring_users}\n"
            f"└ Забанено: {banned_users}\n\n"
            "<b>📈 Регистрации:</b>\n"
            f"├ Сегодня: {new_today}\n"
            f"└ За 7 дней: {new_week}\n\n"
            "<b>📋 Группы:</b>\n"
            f"├ Всего: {total_groups}\n"
            f"└ Активных: {enabled_groups}\n\n"
            "<b>📦 Заказы:</b>\n"
            f"├ Всего: {total_orders}\n"
            f"├ Сегодня: {orders_today}\n"
            f"└ С откликом: {responded_orders}\n\n"
            "<b>💰 Платежи:</b>\n"
            f"├ Подтверждённых: {confirmed_payments}\n"
            f"└ Сумма: {total_revenue:.0f} руб.\n\n"
            f"<i>{datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC</i>"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_back_to_admin_menu(),
        )


# === СПИСОК ПОЛЬЗОВАТЕЛЕЙ ===

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(20)
        )
        users = result.scalars().all()

        text = "📋 <b>Последние 20 пользователей:</b>\n\n"

        for user in users:
            status = []
            if user.is_banned:
                status.append("🚫 бан")
            if user.is_admin:
                status.append("👑 админ")
            if user.is_subscription_active:
                status.append("💳")
            if user.monitoring_enabled:
                status.append("🔔")

            status_str = " ".join(status) if status else "—"
            username = f"@{user.username}" if user.username else "—"

            text += f"• <code>{user.telegram_id}</code> {username} {status_str}\n"

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_back_to_admin_menu(),
        )


# === РАССЫЛКА ===

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_broadcast_message)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки всем пользователям.\n"
        "Поддерживается текст, фото, видео.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_message)
async def admin_broadcast_process(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "Рассылка отменена.",
            reply_markup=get_admin_menu(),
        )
        return

    await state.clear()

    async with async_session() as session:
        users = await UserCRUD.get_all_users(session)

    success = 0
    failed = 0

    status_msg = await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")

    for user in users:
        if user.is_banned:
            continue
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            elif message.video:
                await bot.send_video(
                    chat_id=user.telegram_id,
                    video=message.video.file_id,
                    caption=message.caption,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message.text,
                    parse_mode="HTML",
                )
            success += 1
        except Exception as e:
            logger.error(f"Broadcast error to {user.telegram_id}: {e}")
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {success}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML",
    )
    await message.answer("Админ-панель:", reply_markup=get_admin_menu())


# === БАН / РАЗБАН ===

@router.callback_query(F.data == "admin_ban")
async def admin_ban_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_ban)
    await callback.message.edit_text(
        "🚫 <b>Бан пользователя</b>\n\n"
        "Отправьте Telegram ID пользователя для бана.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_user_id_for_ban)
async def admin_ban_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Отправьте число.")
        return

    async with async_session() as session:
        user = await UserCRUD.search_user_by_telegram_id(session, target_id)

        if not user:
            await message.answer("❌ Пользователь не найден.")
            return

        if user.telegram_id in config.bot.admin_ids:
            await message.answer("❌ Нельзя забанить суперадмина!")
            return

        await UserCRUD.set_banned(session, user.id, True)
        # Отключаем мониторинг
        await UserCRUD.toggle_monitoring(session, user.id, False)

    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> забанен!",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_unban")
async def admin_unban_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_unban)
    await callback.message.edit_text(
        "✅ <b>Разбан пользователя</b>\n\n"
        "Отправьте Telegram ID пользователя для разбана.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_user_id_for_unban)
async def admin_unban_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Отправьте число.")
        return

    async with async_session() as session:
        user = await UserCRUD.search_user_by_telegram_id(session, target_id)

        if not user:
            await message.answer("❌ Пользователь не найден.")
            return

        await UserCRUD.set_banned(session, user.id, False)

    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> разбанен!",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


# === УПРАВЛЕНИЕ АДМИНАМИ ===

@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_admin)
    await callback.message.edit_text(
        "👑 <b>Назначить админа</b>\n\n"
        "Отправьте Telegram ID пользователя.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_user_id_for_admin)
async def admin_add_admin_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Отправьте число.")
        return

    async with async_session() as session:
        user = await UserCRUD.search_user_by_telegram_id(session, target_id)

        if not user:
            await message.answer("❌ Пользователь не найден. Он должен сначала написать боту.")
            return

        await UserCRUD.set_admin(session, user.id, True)

    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> назначен админом!",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_user_id_for_remove_admin)
    await callback.message.edit_text(
        "👤 <b>Снять права админа</b>\n\n"
        "Отправьте Telegram ID пользователя.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_user_id_for_remove_admin)
async def admin_remove_admin_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Отправьте число.")
        return

    if target_id in config.bot.admin_ids:
        await message.answer("❌ Нельзя снять права суперадмина из конфига!")
        return

    async with async_session() as session:
        user = await UserCRUD.search_user_by_telegram_id(session, target_id)

        if not user:
            await message.answer("❌ Пользователь не найден.")
            return

        await UserCRUD.set_admin(session, user.id, False)

    await state.clear()
    await message.answer(
        f"✅ Права админа сняты с <code>{target_id}</code>!",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_list_admins")
async def admin_list_admins(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        admins = await UserCRUD.get_all_admins(session)

    text = "👑 <b>Список админов:</b>\n\n"

    # Суперадмины из конфига
    text += "<b>Суперадмины (из конфига):</b>\n"
    for admin_id in config.bot.admin_ids:
        text += f"• <code>{admin_id}</code>\n"

    # Админы из БД
    if admins:
        text += "\n<b>Назначенные админы:</b>\n"
        for admin in admins:
            username = f"@{admin.username}" if admin.username else "—"
            text += f"• <code>{admin.telegram_id}</code> {username}\n"
    else:
        text += "\n<i>Назначенных админов нет</i>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_back_to_admin_menu(),
    )
