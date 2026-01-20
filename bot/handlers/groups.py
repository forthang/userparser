from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupCRUD
from bot.keyboards.main_menu import MainMenuText, get_cancel_keyboard, get_main_menu
from bot.keyboards.groups_kb import get_groups_keyboard, get_groups_empty_keyboard
from bot.services.userbot import UserBotService
from bot.config import config
from bot.utils.fuzzy_search import find_best_match

router = Router()


class GroupStates(StatesGroup):
    waiting_search = State()
    waiting_bulk_names = State()


@router.message(F.text == MainMenuText.GROUPS)
async def groups_menu(message: Message, state: FSMContext):
    await state.clear()

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
async def groups_refresh(callback: CallbackQuery, state: FSMContext):
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

            # Получаем поисковый запрос если был
            data = await state.get_data()
            search_query = data.get("groups_search")

            enabled_count = len([g for g in groups if g.is_enabled])
            await callback.message.edit_text(
                f"📋 <b>Список групп</b>\n\n"
                f"✅ Загружено групп: {len(groups)}\n"
                f"Выбрано для мониторинга: {enabled_count}\n\n"
                f"✅ - группа добавлена для мониторинга\n"
                f"⬜ - группа не отслеживается\n\n"
                f"Нажмите на группу, чтобы включить/выключить мониторинг:",
                parse_mode="HTML",
                reply_markup=get_groups_keyboard(groups, page=0, search_query=search_query),
            )

        except Exception as e:
            await callback.message.edit_text(
                f"❌ Ошибка при загрузке групп: {str(e)}\n\n"
                "Возможно, сессия истекла. Попробуйте авторизоваться заново.",
                reply_markup=get_groups_empty_keyboard(),
            )


@router.callback_query(F.data.startswith("groups_page:"))
async def groups_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка. Нажмите /start")
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)

        # Получаем поисковый запрос если был
        data = await state.get_data()
        search_query = data.get("groups_search")

        await callback.message.edit_reply_markup(
            reply_markup=get_groups_keyboard(groups, page=page, search_query=search_query),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("group_toggle:"))
async def group_toggle(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    group_id = int(parts[1])
    # Получаем текущую страницу из callback_data или 0 по умолчанию
    current_page = int(parts[2]) if len(parts) > 2 else 0

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка")
            return

        is_enabled = await GroupCRUD.toggle_group(session, group_id)

        groups = await GroupCRUD.get_user_groups(session, user.id)

        status = "включена ✅" if is_enabled else "выключена"
        await callback.answer(f"Группа {status}")

        # Получаем поисковый запрос если был
        data = await state.get_data()
        search_query = data.get("groups_search")

        enabled_count = len([g for g in groups if g.is_enabled])
        await callback.message.edit_text(
            f"📋 <b>Список групп</b>\n\n"
            f"Всего групп: {len(groups)}\n"
            f"Выбрано для мониторинга: {enabled_count}\n\n"
            f"✅ - группа добавлена для мониторинга\n"
            f"⬜ - группа не отслеживается\n\n"
            f"Нажмите на группу, чтобы включить/выключить мониторинг:",
            parse_mode="HTML",
            reply_markup=get_groups_keyboard(groups, page=current_page, search_query=search_query),
        )


# === ПОИСК ===

@router.callback_query(F.data == "groups_search")
async def groups_search_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GroupStates.waiting_search)
    await callback.message.answer(
        "🔍 Введите название группы для поиска:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(GroupStates.waiting_search)
async def groups_search_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            if user:
                groups = await GroupCRUD.get_user_groups(session, user.id)
                enabled_count = len([g for g in groups if g.is_enabled])
                await message.answer(
                    "Поиск отменён.",
                    reply_markup=get_main_menu(user.monitoring_enabled),
                )
                await message.answer(
                    f"📋 <b>Список групп</b>\n\n"
                    f"Всего групп: {len(groups)}\n"
                    f"Выбрано для мониторинга: {enabled_count}",
                    parse_mode="HTML",
                    reply_markup=get_groups_keyboard(groups, page=0),
                )
        return

    search_query = message.text.strip()

    await state.set_state(None)
    await state.update_data(groups_search=search_query)

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)

        # Считаем найденные
        found = [g for g in groups if search_query.lower() in g.group_name.lower()]
        enabled_count = len([g for g in groups if g.is_enabled])

        await message.answer(
            f"📋 <b>Список групп</b>\n\n"
            f"Найдено: {len(found)} из {len(groups)}\n"
            f"Выбрано для мониторинга: {enabled_count}",
            parse_mode="HTML",
            reply_markup=get_main_menu(user.monitoring_enabled),
        )
        await message.answer(
            "Результаты поиска:",
            reply_markup=get_groups_keyboard(groups, page=0, search_query=search_query),
        )


@router.callback_query(F.data == "groups_clear_search")
async def groups_clear_search(callback: CallbackQuery, state: FSMContext):
    await state.update_data(groups_search=None)

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)
        enabled_count = len([g for g in groups if g.is_enabled])

        await callback.message.edit_text(
            f"📋 <b>Список групп</b>\n\n"
            f"Всего групп: {len(groups)}\n"
            f"Выбрано для мониторинга: {enabled_count}\n\n"
            f"✅ - группа добавлена для мониторинга\n"
            f"⬜ - группа не отслеживается",
            parse_mode="HTML",
            reply_markup=get_groups_keyboard(groups, page=0),
        )
        await callback.answer("Поиск сброшен")


# === МАССОВОЕ ВКЛЮЧЕНИЕ ПО НАЗВАНИЯМ ===

@router.callback_query(F.data == "groups_bulk_enable")
async def groups_bulk_enable_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GroupStates.waiting_bulk_names)
    await callback.message.answer(
        "📝 <b>Массовое включение групп</b>\n\n"
        "Введите названия групп (каждое с новой строки или через запятую).\n"
        "Группы будут включены по частичному совпадению названия.\n\n"
        "Пример:\n"
        "<code>Такси Москва\n"
        "Водители СПб\n"
        "Трансфер</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(GroupStates.waiting_bulk_names)
async def groups_bulk_enable_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            if user:
                groups = await GroupCRUD.get_user_groups(session, user.id)
                await message.answer(
                    "Отменено.",
                    reply_markup=get_main_menu(user.monitoring_enabled),
                )
                await message.answer(
                    "📋 <b>Список групп</b>",
                    parse_mode="HTML",
                    reply_markup=get_groups_keyboard(groups, page=0),
                )
        return

    # Парсим названия - разделитель: запятая или новая строка
    text = message.text.strip()
    names = []
    for line in text.replace(",", "\n").split("\n"):
        name = line.strip()
        if name:
            names.append(name.lower())

    if not names:
        await message.answer(
            "❌ Не удалось распознать названия групп. Попробуйте ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка. Нажмите /start")
            await state.clear()
            return

        groups = await GroupCRUD.get_user_groups(session, user.id)

        enabled_groups = []
        not_found_names = []
        fuzzy_matches = []  # группы найденные через fuzzy-match

        for search_name in names:
            # Сначала пробуем точное вхождение
            exact_match = None
            for group in groups:
                if search_name in group.group_name.lower():
                    exact_match = group
                    break

            if exact_match:
                if not exact_match.is_enabled:
                    await GroupCRUD.toggle_group(session, exact_match.id)
                    enabled_groups.append(exact_match.group_name)
                else:
                    enabled_groups.append(f"{exact_match.group_name} (уже была)")
            else:
                # Используем fuzzy-matching
                best_match, score = find_best_match(
                    search_name,
                    groups,
                    lambda g: g.group_name,
                    threshold=0.4
                )

                if best_match:
                    if not best_match.is_enabled:
                        await GroupCRUD.toggle_group(session, best_match.id)
                        fuzzy_matches.append(f"{search_name} -> {best_match.group_name}")
                        enabled_groups.append(f"{best_match.group_name} (нашли похожую)")
                    else:
                        fuzzy_matches.append(f"{search_name} -> {best_match.group_name} (уже была)")
                        enabled_groups.append(f"{best_match.group_name} (уже была)")
                else:
                    not_found_names.append(search_name)

        await state.clear()

        groups = await GroupCRUD.get_user_groups(session, user.id)
        enabled_count = len([g for g in groups if g.is_enabled])

        result_text = f"📋 <b>Результат</b>\n\n"

        if enabled_groups:
            result_text += f"✅ Включено групп: {len(enabled_groups)}\n"
            for g in enabled_groups[:10]:
                result_text += f"• {g}\n"
            if len(enabled_groups) > 10:
                result_text += f"... и ещё {len(enabled_groups) - 10}\n"

        if fuzzy_matches:
            result_text += f"\n🔍 Найдено по похожести:\n"
            for fm in fuzzy_matches[:5]:
                result_text += f"• {fm}\n"
            if len(fuzzy_matches) > 5:
                result_text += f"... и ещё {len(fuzzy_matches) - 5}\n"

        if not_found_names:
            result_text += f"\n❌ Не найдено: {len(not_found_names)}\n"
            for n in not_found_names[:5]:
                result_text += f"• {n}\n"
            if len(not_found_names) > 5:
                result_text += f"... и ещё {len(not_found_names) - 5}\n"

        result_text += f"\n📊 Всего выбрано для мониторинга: {enabled_count}"

        await message.answer(
            result_text,
            parse_mode="HTML",
            reply_markup=get_main_menu(user.monitoring_enabled),
        )
        await message.answer(
            "📋 <b>Список групп</b>",
            parse_mode="HTML",
            reply_markup=get_groups_keyboard(groups, page=0),
        )
