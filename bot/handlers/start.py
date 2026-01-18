from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD
from bot.keyboards.main_menu import (
    get_main_menu, get_auth_keyboard, get_cancel_keyboard,
    get_code_keyboard, get_2fa_keyboard, get_letters_keyboard, get_symbols_keyboard
)
from bot.services.userbot import UserBotService
from bot.config import config

router = Router()


class AuthStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # Очищаем сессию авторизации если была
    UserBotService.cleanup_auth(message.from_user.id)

    async with async_session() as session:
        user = await UserCRUD.get_or_create(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        if user.session_string:
            text = (
                f"Добро пожаловать, {message.from_user.first_name}!\n\n"
                f"✅ Ваш аккаунт подключен\n"
            )
            if user.is_subscription_active:
                text += f"📅 Подписка активна до: {user.subscription_end.strftime('%d.%m.%Y')}\n"
                text += f"🔔 Мониторинг: {'Включен' if user.monitoring_enabled else 'Выключен'}"
            else:
                text += "⚠️ Подписка не активна. Оформите подписку для начала работы."

            await message.answer(
                text,
                reply_markup=get_main_menu(user.monitoring_enabled),
            )
        else:
            await message.answer(
                f"Добро пожаловать, {message.from_user.first_name}!\n\n"
                "Для начала работы необходимо авторизовать ваш Telegram аккаунт.\n"
                "Это позволит боту отслеживать сообщения в ваших группах.\n\n"
                "Нажмите кнопку ниже для авторизации:",
                reply_markup=get_auth_keyboard(),
            )


@router.callback_query(F.data == "auth_start")
async def auth_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AuthStates.waiting_phone)
    await callback.message.answer(
        "📱 Введите ваш номер телефона в международном формате:\n"
        "Например: +79001234567",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(AuthStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        UserBotService.cleanup_auth(message.from_user.id)
        await message.answer(
            "Авторизация отменена.",
            reply_markup=get_auth_keyboard(),
        )
        return

    phone = message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    if not phone[1:].isdigit() or len(phone) < 10:
        await message.answer(
            "❌ Неверный формат номера. Введите номер в формате +79001234567",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(phone=phone)

    status_msg = await message.answer("⏳ Отправляю код подтверждения...")

    try:
        phone_code_hash = await UserBotService.send_code(
            api_id=config.telegram_api.api_id,
            api_hash=config.telegram_api.api_hash,
            phone=phone,
            user_id=message.from_user.id,
        )

        await state.update_data(phone_code_hash=phone_code_hash, code="")
        await state.set_state(AuthStates.waiting_code)

        await status_msg.edit_text(
            "✅ Код отправлен!\n\n"
            "Введите код подтверждения с помощью клавиатуры ниже.\n"
            "Код придёт в Telegram (не SMS).",
            reply_markup=get_code_keyboard(""),
        )

    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка при отправке кода: {str(e)}\n"
            "Попробуйте ещё раз или обратитесь в поддержку."
        )
        await state.clear()


# === Обработчики инлайн клавиатуры для кода ===

@router.callback_query(F.data == "code_display")
async def code_display_handler(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("code_") & ~F.data.in_(["code_display", "code_backspace", "code_submit", "code_cancel"]))
async def code_digit_handler(callback: CallbackQuery, state: FSMContext):
    """Обработка нажатия цифры"""
    digit = callback.data.replace("code_", "")

    data = await state.get_data()
    current_code = data.get("code", "")

    if len(current_code) < 6:  # Максимум 6 цифр
        current_code += digit
        await state.update_data(code=current_code)

    await callback.message.edit_reply_markup(
        reply_markup=get_code_keyboard(current_code)
    )
    await callback.answer()


@router.callback_query(F.data == "code_backspace")
async def code_backspace_handler(callback: CallbackQuery, state: FSMContext):
    """Удаление последней цифры"""
    data = await state.get_data()
    current_code = data.get("code", "")

    if current_code:
        current_code = current_code[:-1]
        await state.update_data(code=current_code)

    await callback.message.edit_reply_markup(
        reply_markup=get_code_keyboard(current_code)
    )
    await callback.answer()


@router.callback_query(F.data == "code_submit")
async def code_submit_handler(callback: CallbackQuery, state: FSMContext):
    """Отправка кода"""
    data = await state.get_data()
    code = data.get("code", "")
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")

    if len(code) < 5:
        await callback.answer("Введите полный код (минимум 5 цифр)", show_alert=True)
        return

    await callback.answer("Проверяю код...")

    try:
        await callback.message.edit_text("⏳ Проверяю код...")

        result = await UserBotService.sign_in(
            user_id=callback.from_user.id,
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )

        if result.get("need_2fa"):
            await state.set_state(AuthStates.waiting_2fa)
            await state.update_data(password="")
            await callback.message.edit_text(
                "🔐 У вас включена двухфакторная аутентификация.\n"
                "Введите ваш облачный пароль с помощью клавиатуры:",
                reply_markup=get_2fa_keyboard(""),
            )
            return

        session_string = result.get("session_string")

        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
            if user:
                await UserCRUD.update_session(session, user.id, session_string, phone)

        await state.clear()
        await callback.message.edit_text(
            "✅ Авторизация успешна!\n\n"
            "Теперь вы можете:\n"
            "• Выбрать группы для мониторинга\n"
            "• Настроить ключевые слова\n"
            "• Добавить города\n"
            "• Оформить подписку и запустить мониторинг"
        )

        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
            await callback.message.answer(
                "Главное меню:",
                reply_markup=get_main_menu(user.monitoring_enabled if user else False),
            )

    except Exception as e:
        error_msg = str(e).lower()
        if "phone_code_invalid" in error_msg or "invalid" in error_msg:
            await state.update_data(code="")
            await callback.message.edit_text(
                "❌ Неверный код. Попробуйте ввести код ещё раз.",
                reply_markup=get_code_keyboard(""),
            )
        elif "phone_code_expired" in error_msg or "expired" in error_msg:
            await callback.message.edit_text(
                "❌ Код истёк. Начните авторизацию заново.",
                reply_markup=get_auth_keyboard(),
            )
            UserBotService.cleanup_auth(callback.from_user.id)
            await state.clear()
        else:
            await callback.message.edit_text(
                f"❌ Ошибка авторизации: {str(e)}\n"
                "Попробуйте ещё раз.",
                reply_markup=get_auth_keyboard(),
            )
            UserBotService.cleanup_auth(callback.from_user.id)
            await state.clear()


@router.callback_query(F.data == "code_cancel")
async def code_cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода кода"""
    await callback.answer()
    await state.clear()
    UserBotService.cleanup_auth(callback.from_user.id)

    await callback.message.edit_text(
        "Авторизация отменена.",
        reply_markup=get_auth_keyboard(),
    )


# === Обработчики инлайн клавиатуры для 2FA пароля ===

@router.callback_query(F.data == "2fa_display")
async def twofa_display_handler(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.regexp(r"^2fa_[0-9]$"))
async def twofa_digit_handler(callback: CallbackQuery, state: FSMContext):
    """Обработка нажатия цифры в 2FA"""
    digit = callback.data.replace("2fa_", "")

    data = await state.get_data()
    current_password = data.get("password", "")
    current_password += digit
    await state.update_data(password=current_password)

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_backspace")
async def twofa_backspace_handler(callback: CallbackQuery, state: FSMContext):
    """Удаление последнего символа"""
    data = await state.get_data()
    current_password = data.get("password", "")

    if current_password:
        current_password = current_password[:-1]
        await state.update_data(password=current_password)

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_letters")
async def twofa_letters_handler(callback: CallbackQuery):
    """Показать клавиатуру с маленькими буквами"""
    await callback.message.edit_reply_markup(
        reply_markup=get_letters_keyboard(uppercase=False)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_LETTERS")
async def twofa_upper_letters_handler(callback: CallbackQuery):
    """Показать клавиатуру с большими буквами"""
    await callback.message.edit_reply_markup(
        reply_markup=get_letters_keyboard(uppercase=True)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_symbols")
async def twofa_symbols_handler(callback: CallbackQuery):
    """Показать клавиатуру с символами"""
    await callback.message.edit_reply_markup(
        reply_markup=get_symbols_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("2fa_lower_"))
async def twofa_lower_letter_handler(callback: CallbackQuery, state: FSMContext):
    """Добавить маленькую букву"""
    letter = callback.data.replace("2fa_lower_", "")

    data = await state.get_data()
    current_password = data.get("password", "")
    current_password += letter
    await state.update_data(password=current_password)

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("2fa_upper_"))
async def twofa_upper_letter_handler(callback: CallbackQuery, state: FSMContext):
    """Добавить большую букву"""
    letter = callback.data.replace("2fa_upper_", "")

    data = await state.get_data()
    current_password = data.get("password", "")
    current_password += letter
    await state.update_data(password=current_password)

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("2fa_sym_"))
async def twofa_symbol_handler(callback: CallbackQuery, state: FSMContext):
    """Добавить символ"""
    symbol = callback.data.replace("2fa_sym_", "")

    data = await state.get_data()
    current_password = data.get("password", "")
    current_password += symbol
    await state.update_data(password=current_password)

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_back_to_main")
async def twofa_back_handler(callback: CallbackQuery, state: FSMContext):
    """Вернуться к основной клавиатуре 2FA"""
    data = await state.get_data()
    current_password = data.get("password", "")

    await callback.message.edit_reply_markup(
        reply_markup=get_2fa_keyboard(current_password)
    )
    await callback.answer()


@router.callback_query(F.data == "2fa_submit")
async def twofa_submit_handler(callback: CallbackQuery, state: FSMContext):
    """Отправка 2FA пароля"""
    data = await state.get_data()
    password = data.get("password", "")
    phone = data.get("phone")

    if not password:
        await callback.answer("Введите пароль", show_alert=True)
        return

    await callback.answer("Проверяю пароль...")

    try:
        await callback.message.edit_text("⏳ Проверяю пароль...")

        session_string = await UserBotService.check_password(
            user_id=callback.from_user.id,
            password=password,
        )

        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
            if user:
                await UserCRUD.update_session(session, user.id, session_string, phone)

        await state.clear()
        await callback.message.edit_text(
            "✅ Авторизация успешна!\n\n"
            "Теперь вы можете настроить бота и запустить мониторинг."
        )

        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
            await callback.message.answer(
                "Главное меню:",
                reply_markup=get_main_menu(user.monitoring_enabled if user else False),
            )

    except Exception as e:
        await state.update_data(password="")
        await callback.message.edit_text(
            f"❌ Неверный пароль или ошибка: {str(e)}\n"
            "Попробуйте ещё раз.",
            reply_markup=get_2fa_keyboard(""),
        )


@router.callback_query(F.data == "2fa_cancel")
async def twofa_cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Отмена 2FA"""
    await callback.answer()
    await state.clear()
    UserBotService.cleanup_auth(callback.from_user.id)

    await callback.message.edit_text(
        "Авторизация отменена.",
        reply_markup=get_auth_keyboard(),
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if user and user.session_string:
            text = "Главное меню"
            await callback.message.answer(
                text,
                reply_markup=get_main_menu(user.monitoring_enabled),
            )
        else:
            await callback.message.answer(
                "Для начала работы авторизуйте ваш аккаунт:",
                reply_markup=get_auth_keyboard(),
            )


@router.message(F.text == "❓ Помощь")
async def help_handler(message: Message):
    await message.answer(
        "📚 <b>Справка по боту</b>\n\n"
        "<b>📋 Список групп</b> - выберите группы, в которых бот будет искать заказы\n\n"
        "<b>🔤 Ключевые слова</b> - слова, по которым бот определяет заказы "
        "(заказ, трансфер, такси и т.д.)\n\n"
        "<b>🏙 Города</b> - добавьте города, чтобы бот искал заказы только по ним\n\n"
        "<b>▶️ Мониторинг</b> - включите/выключите отслеживание заказов\n\n"
        "<b>💳 Подписка</b> - оформите или продлите подписку\n\n"
        "❓ Остались вопросы? Напишите в поддержку.",
        parse_mode="HTML",
    )


@router.message(F.text == "⚙️ Настройки")
async def settings_handler(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"📱 Телефон: {user.phone or 'Не указан'}\n"
            f"🔗 Аккаунт: {'Подключен ✅' if user.session_string else 'Не подключен ❌'}\n"
            f"📅 Подписка до: {user.subscription_end.strftime('%d.%m.%Y') if user.subscription_end else 'Не активна'}\n"
            f"🔔 Мониторинг: {'Включен ✅' if user.monitoring_enabled else 'Выключен ❌'}\n"
        )

        await message.answer(text, parse_mode="HTML")
