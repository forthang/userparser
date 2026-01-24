from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, KeywordCRUD
from bot.keyboards.main_menu import MainMenuText, get_cancel_keyboard, get_main_menu
from bot.keyboards.inline import (
    get_keywords_keyboard,
    get_keyword_confirm_delete,
    get_keyword_confirm_delete_all,
)

router = Router()


class KeywordStates(StatesGroup):
    waiting_word = State()
    waiting_bulk_words = State()
    confirm_delete = State()


@router.message(F.text == MainMenuText.KEYWORDS)
async def keywords_menu(message: Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

        await message.answer(
            f"🔤 <b>Ключевые слова</b>\n\n"
            f"Всего слов: {len(keywords)}\n\n"
            f"Бот ищет заказы, содержащие эти слова.\n"
            f"Поиск умный: учитывает разные формы слов (заказ/заказа/заказы).",
            parse_mode="HTML",
            reply_markup=get_keywords_keyboard(keywords),
        )


@router.callback_query(F.data == "kw_add")
async def keyword_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(KeywordStates.waiting_word)
    await callback.message.answer(
        "📝 Введите новое ключевое слово или фразу:\n"
        "(например: нужен водитель)",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(KeywordStates.waiting_word)
async def keyword_add_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            keywords = await KeywordCRUD.get_user_keywords(session, user.id)
            await message.answer(
                "Отменено.",
                reply_markup=get_main_menu(user.monitoring_enabled if user else False),
            )
            await message.answer(
                "🔤 <b>Ключевые слова</b>",
                parse_mode="HTML",
                reply_markup=get_keywords_keyboard(keywords),
            )
        return

    word = message.text.strip().lower()

    if len(word) < 2:
        await message.answer(
            "❌ Слово слишком короткое. Введите минимум 2 символа.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    if len(word) > 100:
        await message.answer(
            "❌ Слово слишком длинное. Максимум 100 символов.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            await state.clear()
            return

        existing = await KeywordCRUD.get_user_keywords(session, user.id)
        existing_words = {k.word.lower() for k in existing}

        # Добавляем слово как есть (без склонений)
        added = False
        if word.lower() not in existing_words:
            await KeywordCRUD.add_keyword(session, user.id, word)
            added = True

        await state.clear()

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

        if added:
            await message.answer(
                f"✅ Слово «{word}» добавлено!",
                reply_markup=get_main_menu(user.monitoring_enabled),
            )
        else:
            await message.answer(
                f"⚠️ Слово «{word}» уже есть в списке.",
                reply_markup=get_main_menu(user.monitoring_enabled),
            )
        await message.answer(
            "🔤 <b>Ключевые слова</b>",
            parse_mode="HTML",
            reply_markup=get_keywords_keyboard(keywords),
        )


@router.callback_query(F.data.startswith("kw_page:"))
async def keyword_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Ошибка")
            return

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

        await callback.message.edit_reply_markup(
            reply_markup=get_keywords_keyboard(keywords, page=page),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("kw_delete:"))
async def keyword_delete(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    keyword_id = int(parts[1])
    current_page = int(parts[2]) if len(parts) > 2 else 0
    await state.update_data(delete_keyword_id=keyword_id, kw_page=current_page)

    await callback.message.edit_text(
        "⚠️ Удалить это ключевое слово?",
        reply_markup=get_keyword_confirm_delete(),
    )


@router.callback_query(F.data == "kw_confirm_delete")
async def keyword_confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    keyword_id = data.get("delete_keyword_id")
    current_page = data.get("kw_page", 0)

    if not keyword_id:
        await callback.answer("Ошибка")
        return

    async with async_session() as session:
        await KeywordCRUD.delete_keyword(session, keyword_id)

        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

    await state.clear()
    await callback.answer("✅ Слово удалено")

    await callback.message.edit_text(
        "🔤 <b>Ключевые слова</b>",
        parse_mode="HTML",
        reply_markup=get_keywords_keyboard(keywords, page=current_page),
    )


@router.callback_query(F.data == "kw_delete_all")
async def keyword_delete_all_ask(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы уверены, что хотите удалить ВСЕ ключевые слова?\n"
        "Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=get_keyword_confirm_delete_all(),
    )


@router.callback_query(F.data == "kw_confirm_delete_all")
async def keyword_confirm_delete_all(callback: CallbackQuery):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка")
            return

        await KeywordCRUD.delete_all_keywords(session, user.id)

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

    await callback.answer("✅ Все слова удалены")

    await callback.message.edit_text(
        "🔤 <b>Ключевые слова</b>\n\n"
        "Список пуст. Добавьте новые слова или восстановите базовые.",
        parse_mode="HTML",
        reply_markup=get_keywords_keyboard(keywords),
    )


@router.callback_query(F.data == "kw_reset")
async def keyword_reset_ask(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ <b>Сброс к стандартным</b>\n\n"
        "Текущие ключевые слова будут удалены и заменены на базовый набор.\n"
        "Продолжить?",
        parse_mode="HTML",
        reply_markup=get_keyword_confirm_reset(),
    )


@router.callback_query(F.data == "kw_confirm_reset")
async def keyword_confirm_reset(callback: CallbackQuery):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка")
            return

        await KeywordCRUD.restore_defaults(session, user.id)

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

    await callback.answer("✅ Восстановлены базовые слова")

    await callback.message.edit_text(
        "🔤 <b>Ключевые слова</b>\n\n"
        "Восстановлен базовый набор ключевых слов.",
        parse_mode="HTML",
        reply_markup=get_keywords_keyboard(keywords),
    )


@router.callback_query(F.data == "kw_cancel")
async def keyword_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

    await callback.message.edit_text(
        "🔤 <b>Ключевые слова</b>",
        parse_mode="HTML",
        reply_markup=get_keywords_keyboard(keywords),
    )


@router.callback_query(F.data.startswith("kw_info:"))
async def keyword_info(callback: CallbackQuery):
    await callback.answer("Нажмите 🗑 для удаления")


# === МАССОВОЕ ДОБАВЛЕНИЕ ===

@router.callback_query(F.data == "kw_bulk_add")
async def keyword_bulk_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(KeywordStates.waiting_bulk_words)
    await callback.message.answer(
        "📝 <b>Массовое добавление ключевых слов</b>\n\n"
        "Введите ключевые слова (каждое с новой строки или через запятую).\n"
        "Для каждого слова автоматически добавятся его склонения.\n\n"
        "Пример:\n"
        "<code>заказ\n"
        "трансфер\n"
        "нужен водитель</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(KeywordStates.waiting_bulk_words)
async def keyword_bulk_add_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            keywords = await KeywordCRUD.get_user_keywords(session, user.id)
            await message.answer(
                "Отменено.",
                reply_markup=get_main_menu(user.monitoring_enabled if user else False),
            )
            await message.answer(
                "🔤 <b>Ключевые слова</b>",
                parse_mode="HTML",
                reply_markup=get_keywords_keyboard(keywords),
            )
        return

    # Парсим слова - разделитель: запятая или новая строка
    text = message.text.strip()
    words = []
    for line in text.replace(",", "\n").split("\n"):
        word = line.strip().lower()
        if word and len(word) >= 2:
            words.append(word)

    if not words:
        await message.answer(
            "❌ Не удалось распознать ключевые слова. Минимум 2 символа.\n"
            "Попробуйте ещё раз.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка. Нажмите /start")
            await state.clear()
            return

        existing = await KeywordCRUD.get_user_keywords(session, user.id)
        existing_words = {k.word.lower() for k in existing}

        added_words = []

        for word in words:
            # Добавляем слово как есть (без склонений)
            if word.lower() not in existing_words:
                await KeywordCRUD.add_keyword(session, user.id, word)
                existing_words.add(word.lower())
                added_words.append(word)

        await state.clear()

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

        if added_words:
            sample = added_words[:10]
            sample_text = ", ".join(sample)
            if len(added_words) > 10:
                sample_text += f" и ещё {len(added_words) - 10}"

            await message.answer(
                f"✅ Добавлено слов: {len(added_words)}\n\n"
                f"{sample_text}",
                reply_markup=get_main_menu(user.monitoring_enabled),
            )
        else:
            await message.answer(
                "⚠️ Все указанные слова уже есть в списке.",
                reply_markup=get_main_menu(user.monitoring_enabled),
            )

        await message.answer(
            "🔤 <b>Ключевые слова</b>",
            parse_mode="HTML",
            reply_markup=get_keywords_keyboard(keywords),
        )
