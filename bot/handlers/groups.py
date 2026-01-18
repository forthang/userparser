from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupCRUD
from bot.keyboards.main_menu import MainMenuText
from bot.keyboards.groups_kb import get_groups_keyboard, get_groups_empty_keyboard
from bot.services.userbot import UserBotService
from bot.config import config

router = Router()


@router.message(F.text == MainMenuText.GROUPS)
async def groups_menu(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user or not user.session_string:
            await message.answer(
                "⚠️ Сначала авторизуйте ваш аккаунт.\n"
                "Нажмите /start для начала."
            )
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)

        if not groups:
            await message.answer(
                "📋 <b>Список групп</b>\n\n"
                "У вас пока нет групп. Нажмите кнопку ниже, "
                "чтобы загрузить список групп из вашего аккаунта.",
                parse_mode="HTML",
                reply_markup=get_groups_empty_keyboard(),
            )
        else:
            enabled_count = len([g for g in groups if g.is_enabled])
            await message.answer(
                f"📋 <b>Список групп</b>\n\n"
                f"Всего групп: {len(groups)}\n"
                f"Выбрано для мониторинга: {enabled_count}\n\n"
                f"✅ - группа добавлена для мониторинга\n"
                f"⬜ - группа не отслеживается\n\n"
                f"Нажмите на группу, чтобы включить/выключить мониторинг:",
                parse_mode="HTML",
                reply_markup=get_groups_keyboard(groups, page=0),
            )


@router.callback_query(F.data == "groups_refresh")
async def groups_refresh(callback: CallbackQuery):
    await callback.answer("⏳ Загружаю группы...")

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user or not user.session_string:
            await callback.message.edit_text(
                "⚠️ Сессия не найдена. Авторизуйтесь заново."
            )
            return

        try:
            userbot = UserBotService(
                api_id=config.telegram_api.api_id,
                api_hash=config.telegram_api.api_hash,
                session_string=user.session_string,
            )

            telegram_groups = await userbot.get_dialogs()

            await GroupCRUD.sync_groups(session, user.id, telegram_groups)

            groups = await GroupCRUD.get_user_groups(session, user.id)

            enabled_count = len([g for g in groups if g.is_enabled])
            await callback.message.edit_text(
                f"📋 <b>Список групп</b>\n\n"
                f"✅ Загружено групп: {len(groups)}\n"
                f"Выбрано для мониторинга: {enabled_count}\n\n"
                f"✅ - группа добавлена для мониторинга\n"
                f"⬜ - группа не отслеживается\n\n"
                f"Нажмите на группу, чтобы включить/выключить мониторинг:",
                parse_mode="HTML",
                reply_markup=get_groups_keyboard(groups, page=0),
            )

        except Exception as e:
            await callback.message.edit_text(
                f"❌ Ошибка при загрузке групп: {str(e)}\n\n"
                "Возможно, сессия истекла. Попробуйте авторизоваться заново.",
                reply_markup=get_groups_empty_keyboard(),
            )


@router.callback_query(F.data.startswith("groups_page:"))
async def groups_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка. Нажмите /start")
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)

        await callback.message.edit_reply_markup(
            reply_markup=get_groups_keyboard(groups, page=page),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("group_toggle:"))
async def group_toggle(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка")
            return

        is_enabled = await GroupCRUD.toggle_group(session, group_id)

        groups = await GroupCRUD.get_user_groups(session, user.id)

        status = "включена" if is_enabled else "выключена"
        await callback.answer(f"Группа {status}")

        enabled_count = len([g for g in groups if g.is_enabled])
        await callback.message.edit_text(
            f"📋 <b>Список групп</b>\n\n"
            f"Всего групп: {len(groups)}\n"
            f"Выбрано для мониторинга: {enabled_count}\n\n"
            f"✅ - группа добавлена для мониторинга\n"
            f"⬜ - группа не отслеживается\n\n"
            f"Нажмите на группу, чтобы включить/выключить мониторинг:",
            parse_mode="HTML",
            reply_markup=get_groups_keyboard(groups, page=0),
        )
