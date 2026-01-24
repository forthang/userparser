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
from bot.database.models import User, Group, Order, Payment, BlacklistedGroup
from bot.database.crud import UserCRUD, BlacklistedGroupCRUD, BotSettingsCRUD
from bot.config import config

logger = logging.getLogger(__name__)

router = Router()

# Скрытые пользователи (не отображаются в статистике и списках)
HIDDEN_USER_IDS = {818978639}


class AdminStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_user_id_for_ban = State()
    waiting_user_id_for_unban = State()
    waiting_user_id_for_admin = State()
    waiting_user_id_for_remove_admin = State()
    waiting_group_to_blacklist = State()
    waiting_group_to_unblacklist = State()
    waiting_help_text = State()
    waiting_subscription_price = State()
    waiting_subscription_days = State()


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
    builder.row(
        InlineKeyboardButton(text="🚷 Черный список групп", callback_data="admin_blacklist"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 Настройки платежей", callback_data="admin_payments"),
    )
    builder.row(
        InlineKeyboardButton(text="❓ Текст помощи", callback_data="admin_help_text"),
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
        # Базовый фильтр - исключаем скрытых пользователей
        hidden_filter = User.telegram_id.notin_(HIDDEN_USER_IDS)

        total_users = await session.scalar(
            select(func.count(User.id)).where(hidden_filter)
        )
        active_users = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.subscription_end > datetime.utcnow()
            )
        )
        monitoring_users = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.monitoring_enabled == True
            )
        )
        authorized_users = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.session_string.isnot(None)
            )
        )
        banned_users = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.is_banned == True
            )
        )

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.created_at >= today_start
            )
        )

        week_ago = datetime.utcnow() - timedelta(days=7)
        new_week = await session.scalar(
            select(func.count(User.id)).where(
                hidden_filter,
                User.created_at >= week_ago
            )
        )

        # Группы и заказы скрытых пользователей тоже исключаем
        hidden_user_ids_subq = select(User.id).where(User.telegram_id.in_(HIDDEN_USER_IDS))

        total_groups = await session.scalar(
            select(func.count(Group.id)).where(Group.user_id.notin_(hidden_user_ids_subq))
        )
        enabled_groups = await session.scalar(
            select(func.count(Group.id)).where(
                Group.user_id.notin_(hidden_user_ids_subq),
                Group.is_enabled == True
            )
        )

        total_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.user_id.notin_(hidden_user_ids_subq))
        )
        orders_today = await session.scalar(
            select(func.count(Order.id)).where(
                Order.user_id.notin_(hidden_user_ids_subq),
                Order.created_at >= today_start
            )
        )
        responded_orders = await session.scalar(
            select(func.count(Order.id)).where(
                Order.user_id.notin_(hidden_user_ids_subq),
                Order.responded == True
            )
        )

        confirmed_payments = await session.scalar(
            select(func.count(Payment.id)).where(
                Payment.user_id.notin_(hidden_user_ids_subq),
                Payment.status == "confirmed"
            )
        )
        total_revenue = await session.scalar(
            select(func.sum(Payment.amount)).where(
                Payment.user_id.notin_(hidden_user_ids_subq),
                Payment.status == "confirmed"
            )
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
            select(User)
            .where(User.telegram_id.notin_(HIDDEN_USER_IDS))
            .order_by(User.created_at.desc())
            .limit(20)
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


# === ЧЕРНЫЙ СПИСОК ГРУПП ===

def get_blacklist_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить группу", callback_data="admin_blacklist_add"),
        InlineKeyboardButton(text="➖ Удалить группу", callback_data="admin_blacklist_remove"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu"),
    )
    return builder.as_markup()


@router.callback_query(F.data == "admin_blacklist")
async def admin_blacklist(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        blacklisted = await BlacklistedGroupCRUD.get_all(session)

    text = "🚷 <b>Черный список групп</b>\n\n"
    text += "Группы из этого списка недоступны для мониторинга.\n\n"

    if blacklisted:
        text += "<b>Заблокированные группы:</b>\n"
        for bg in blacklisted[:20]:
            reason = f" ({bg.reason})" if bg.reason else ""
            text += f"• <code>{bg.telegram_group_id}</code> {bg.group_name}{reason}\n"
        if len(blacklisted) > 20:
            text += f"\n... и ещё {len(blacklisted) - 20}"
    else:
        text += "<i>Список пуст</i>"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_blacklist_menu(),
    )


@router.callback_query(F.data == "admin_blacklist_add")
async def admin_blacklist_add_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_group_to_blacklist)
    await callback.message.edit_text(
        "🚷 <b>Добавить группу в черный список</b>\n\n"
        "Отправьте данные в формате:\n"
        "<code>ID группы | Название | Причина (опционально)</code>\n\n"
        "Пример:\n"
        "<code>-1001234567890 | Спам группа | Много рекламы</code>\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_group_to_blacklist)
async def admin_blacklist_add_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    parts = message.text.split("|")
    if len(parts) < 2:
        await message.answer(
            "❌ Неверный формат. Используйте:\n"
            "<code>ID группы | Название | Причина</code>",
            parse_mode="HTML",
        )
        return

    try:
        group_id = int(parts[0].strip())
        group_name = parts[1].strip()
        reason = parts[2].strip() if len(parts) > 2 else None
    except ValueError:
        await message.answer("❌ ID группы должен быть числом.")
        return

    async with async_session() as session:
        if await BlacklistedGroupCRUD.is_blacklisted(session, group_id):
            await message.answer("⚠️ Эта группа уже в черном списке.")
            await state.clear()
            return

        await BlacklistedGroupCRUD.add(
            session,
            telegram_group_id=group_id,
            group_name=group_name,
            added_by=message.from_user.id,
            reason=reason,
        )

    await state.clear()
    await message.answer(
        f"✅ Группа <b>{group_name}</b> добавлена в черный список!",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_blacklist_remove")
async def admin_blacklist_remove_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_group_to_unblacklist)
    await callback.message.edit_text(
        "🚷 <b>Удалить группу из черного списка</b>\n\n"
        "Отправьте ID группы.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_group_to_unblacklist)
async def admin_blacklist_remove_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        group_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID группы должен быть числом.")
        return

    async with async_session() as session:
        removed = await BlacklistedGroupCRUD.remove(session, group_id)

    await state.clear()

    if removed:
        await message.answer(
            f"✅ Группа <code>{group_id}</code> удалена из черного списка!",
            parse_mode="HTML",
            reply_markup=get_admin_menu(),
        )
    else:
        await message.answer(
            "⚠️ Группа не найдена в черном списке.",
            reply_markup=get_admin_menu(),
        )


# === ТЕКСТ ПОМОЩИ ===

@router.callback_query(F.data == "admin_help_text")
async def admin_help_text(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        current_text = await BotSettingsCRUD.get_help_text(session)

    preview = current_text[:500] + "..." if len(current_text) > 500 else current_text

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin_help_text_edit"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu"),
    )

    await callback.message.edit_text(
        f"❓ <b>Текст помощи</b>\n\n"
        f"Этот текст показывается пользователям при нажатии кнопки «Помощь».\n\n"
        f"<b>Текущий текст:</b>\n{preview}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_help_text_edit")
async def admin_help_text_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_help_text)
    await callback.message.edit_text(
        "✏️ <b>Редактирование текста помощи</b>\n\n"
        "Отправьте новый текст для кнопки «Помощь».\n"
        "Поддерживается HTML форматирование.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_help_text)
async def admin_help_text_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    new_text = message.text.strip()

    if len(new_text) > 4000:
        await message.answer(
            "❌ Текст слишком длинный. Максимум 4000 символов.\n"
            "Отправьте текст покороче или /cancel для отмены."
        )
        return

    async with async_session() as session:
        await BotSettingsCRUD.set_help_text(session, new_text)

    await state.clear()
    await message.answer(
        "✅ Текст помощи обновлён!",
        reply_markup=get_admin_menu(),
    )


# === НАСТРОЙКИ ПЛАТЕЖЕЙ ===

def get_payment_settings_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Платежная система", callback_data="admin_payment_system"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Цена подписки", callback_data="admin_payment_price"),
        InlineKeyboardButton(text="📅 Срок подписки", callback_data="admin_payment_days"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu"),
    )
    return builder.as_markup()


@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        # Получаем текущие настройки
        current_system = await BotSettingsCRUD.get(session, "payment_system", "yukassa")
        current_price = await BotSettingsCRUD.get(session, "subscription_price", str(config.subscription.price))
        current_days = await BotSettingsCRUD.get(session, "subscription_days", str(config.subscription.days))

    # Определяем статус платежных систем
    from bot.services.payment import YukassaPayment, PaymentSystem
    from bot.services.robokassa import RobokassaPayment
    from bot.services.tinkoff import TinkoffPayment

    yukassa_status = "✅ Настроена" if YukassaPayment.is_configured() else "❌ Не настроена"
    robokassa_status = "✅ Настроена" if RobokassaPayment.is_configured() else "❌ Не настроена"
    tinkoff_status = "✅ Настроена" if TinkoffPayment.is_configured() else "❌ Не настроена"

    system_names = {
        "yukassa": "ЮКасса",
        "robokassa": "Робокасса",
        "tinkoff": "Тинькофф",
        "disabled": "Отключена",
    }

    text = (
        "💳 <b>Настройки платежей</b>\n\n"
        f"<b>Активная система:</b> {system_names.get(current_system, current_system)}\n\n"
        f"<b>Статус систем:</b>\n"
        f"├ ЮКасса: {yukassa_status}\n"
        f"├ Робокасса: {robokassa_status}\n"
        f"└ Тинькофф: {tinkoff_status}\n\n"
        f"<b>Цена подписки:</b> {current_price} руб.\n"
        f"<b>Срок подписки:</b> {current_days} дней\n\n"
        f"<i>API ключи настраиваются в файле .env</i>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_payment_settings_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_payment_system")
async def admin_payment_system(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        current_system = await BotSettingsCRUD.get(session, "payment_system", "yukassa")

    from bot.services.payment import YukassaPayment
    from bot.services.robokassa import RobokassaPayment
    from bot.services.tinkoff import TinkoffPayment

    builder = InlineKeyboardBuilder()

    # ЮКасса
    yukassa_text = "ЮКасса"
    if current_system == "yukassa":
        yukassa_text = "✅ " + yukassa_text
    if not YukassaPayment.is_configured():
        yukassa_text += " (не настроена)"
    builder.row(
        InlineKeyboardButton(text=yukassa_text, callback_data="admin_set_payment:yukassa")
    )

    # Робокасса
    robokassa_text = "Робокасса"
    if current_system == "robokassa":
        robokassa_text = "✅ " + robokassa_text
    if not RobokassaPayment.is_configured():
        robokassa_text += " (не настроена)"
    builder.row(
        InlineKeyboardButton(text=robokassa_text, callback_data="admin_set_payment:robokassa")
    )

    # Тинькофф
    tinkoff_text = "Тинькофф"
    if current_system == "tinkoff":
        tinkoff_text = "✅ " + tinkoff_text
    if not TinkoffPayment.is_configured():
        tinkoff_text += " (не настроена)"
    builder.row(
        InlineKeyboardButton(text=tinkoff_text, callback_data="admin_set_payment:tinkoff")
    )

    # Отключить платежи
    disabled_text = "Отключить платежи"
    if current_system == "disabled":
        disabled_text = "✅ " + disabled_text
    builder.row(
        InlineKeyboardButton(text=disabled_text, callback_data="admin_set_payment:disabled")
    )

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_payments")
    )

    await callback.message.edit_text(
        "💳 <b>Выберите платежную систему</b>\n\n"
        "Выбранная система будет использоваться для оплаты подписок.\n\n"
        "<i>Для работы системы необходимо указать API ключи в файле .env</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_payment:"))
async def admin_set_payment_system(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    system = callback.data.split(":")[1]

    from bot.services.payment import YukassaPayment
    from bot.services.robokassa import RobokassaPayment
    from bot.services.tinkoff import TinkoffPayment

    # Проверяем, настроена ли выбранная система
    if system == "yukassa" and not YukassaPayment.is_configured():
        await callback.answer(
            "❌ ЮКасса не настроена. Укажите YUKASSA_SHOP_ID и YUKASSA_SECRET_KEY в .env",
            show_alert=True
        )
        return

    if system == "robokassa" and not RobokassaPayment.is_configured():
        await callback.answer(
            "❌ Робокасса не настроена. Укажите ROBOKASSA_MERCHANT_LOGIN и пароли в .env",
            show_alert=True
        )
        return

    if system == "tinkoff" and not TinkoffPayment.is_configured():
        await callback.answer(
            "❌ Тинькофф не настроена. Укажите TINKOFF_TERMINAL_KEY и TINKOFF_SECRET_KEY в .env",
            show_alert=True
        )
        return

    async with async_session() as session:
        await BotSettingsCRUD.set(session, "payment_system", system)

    system_names = {
        "yukassa": "ЮКасса",
        "robokassa": "Робокасса",
        "tinkoff": "Тинькофф",
        "disabled": "Отключена",
    }

    await callback.answer(f"✅ Установлена система: {system_names.get(system, system)}")

    # Обновляем меню
    await admin_payment_system(callback)


@router.callback_query(F.data == "admin_payment_price")
async def admin_payment_price(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        current_price = await BotSettingsCRUD.get(session, "subscription_price", str(config.subscription.price))

    await state.set_state(AdminStates.waiting_subscription_price)
    await callback.message.edit_text(
        f"💰 <b>Изменение цены подписки</b>\n\n"
        f"Текущая цена: <b>{current_price} руб.</b>\n\n"
        f"Отправьте новую цену (целое число в рублях).\n"
        f"Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_subscription_price)
async def admin_payment_price_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError("Цена должна быть положительной")
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    async with async_session() as session:
        await BotSettingsCRUD.set(session, "subscription_price", str(price))

    await state.clear()
    await message.answer(
        f"✅ Цена подписки установлена: <b>{price} руб.</b>",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )


@router.callback_query(F.data == "admin_payment_days")
async def admin_payment_days(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        current_days = await BotSettingsCRUD.get(session, "subscription_days", str(config.subscription.days))

    await state.set_state(AdminStates.waiting_subscription_days)
    await callback.message.edit_text(
        f"📅 <b>Изменение срока подписки</b>\n\n"
        f"Текущий срок: <b>{current_days} дней</b>\n\n"
        f"Отправьте новый срок (целое число дней).\n"
        f"Для отмены отправьте /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_subscription_days)
async def admin_payment_days_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_admin_menu())
        return

    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError("Срок должен быть положительным")
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    async with async_session() as session:
        await BotSettingsCRUD.set(session, "subscription_days", str(days))

    await state.clear()
    await message.answer(
        f"✅ Срок подписки установлен: <b>{days} дней</b>",
        parse_mode="HTML",
        reply_markup=get_admin_menu(),
    )
