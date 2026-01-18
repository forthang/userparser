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
    get_keyword_confirm_reset,
)

router = Router()


class KeywordStates(StatesGroup):
    waiting_word = State()
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

        default_count = len([k for k in keywords if k.is_default])
        custom_count = len([k for k in keywords if not k.is_default])

        await message.answer(
            f"🔤 <b>Ключевые слова</b>\n\n"
            f"Всего слов: {len(keywords)}\n"
            f"📌 Базовые: {default_count}\n"
            f"📝 Свои: {custom_count}\n\n"
            f"Бот ищет заказы, содержащие эти слова:",
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
        if any(k.word.lower() == word for k in existing):
            await message.answer(
                "⚠️ Такое слово уже есть в списке.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        await KeywordCRUD.add_keyword(session, user.id, word)

        await state.clear()

        keywords = await KeywordCRUD.get_user_keywords(session, user.id)

        await message.answer(
            f"✅ Слово «{word}» добавлено!",
            reply_markup=get_main_menu(user.monitoring_enabled),
        )
        await message.answer(
            "🔤 <b>Ключевые слова</b>",
            parse_mode="HTML",
            reply_markup=get_keywords_keyboard(keywords),
        )


@router.callback_query(F.data.startswith("kw_delete:"))
async def keyword_delete(callback: CallbackQuery, state: FSMContext):
    keyword_id = int(callback.data.split(":")[1])
    await state.update_data(delete_keyword_id=keyword_id)

    await callback.message.edit_text(
        "⚠️ Удалить это ключевое слово?",
        reply_markup=get_keyword_confirm_delete(),
    )


@router.callback_query(F.data == "kw_confirm_delete")
async def keyword_confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    keyword_id = data.get("delete_keyword_id")

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
        reply_markup=get_keywords_keyboard(keywords),
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
