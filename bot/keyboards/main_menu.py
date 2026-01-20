from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


class MainMenuText:
    GROUPS = "📋 Список групп"
    KEYWORDS = "🔤 Ключевые слова"
    CITIES = "🏙 Города"
    MONITORING_ON = "▶️ Включить мониторинг"
    MONITORING_OFF = "⏹ Остановить мониторинг"
    SUBSCRIPTION = "💳 Подписка"
    SETTINGS = "⚙️ Настройки"
    HELP = "❓ Помощь"


def get_main_menu(monitoring_enabled: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    builder.row(
        KeyboardButton(text=MainMenuText.GROUPS),
        KeyboardButton(text=MainMenuText.KEYWORDS),
    )
    builder.row(
        KeyboardButton(text=MainMenuText.SUBSCRIPTION),
    )

    if monitoring_enabled:
        builder.row(KeyboardButton(text=MainMenuText.MONITORING_OFF))
    else:
        builder.row(KeyboardButton(text=MainMenuText.MONITORING_ON))

    builder.row(
        KeyboardButton(text=MainMenuText.SETTINGS),
        KeyboardButton(text=MainMenuText.HELP),
    )

    return builder.as_markup(resize_keyboard=True)


def get_auth_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Авторизоваться", callback_data="auth_start")
    )
    return builder.as_markup()


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


def get_back_keyboard(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data))
    return builder.as_markup()


def get_code_keyboard(current_code: str = "") -> InlineKeyboardMarkup:
    """Инлайн клавиатура для ввода кода подтверждения"""
    builder = InlineKeyboardBuilder()

    # Показываем текущий введённый код
    display = current_code if current_code else "_ _ _ _ _"
    builder.row(
        InlineKeyboardButton(text=f"Код: {display}", callback_data="code_display")
    )

    # Цифровая клавиатура 3x3 + 0
    builder.row(
        InlineKeyboardButton(text="1", callback_data="code_1"),
        InlineKeyboardButton(text="2", callback_data="code_2"),
        InlineKeyboardButton(text="3", callback_data="code_3"),
    )
    builder.row(
        InlineKeyboardButton(text="4", callback_data="code_4"),
        InlineKeyboardButton(text="5", callback_data="code_5"),
        InlineKeyboardButton(text="6", callback_data="code_6"),
    )
    builder.row(
        InlineKeyboardButton(text="7", callback_data="code_7"),
        InlineKeyboardButton(text="8", callback_data="code_8"),
        InlineKeyboardButton(text="9", callback_data="code_9"),
    )
    builder.row(
        InlineKeyboardButton(text="⌫", callback_data="code_backspace"),
        InlineKeyboardButton(text="0", callback_data="code_0"),
        InlineKeyboardButton(text="✓", callback_data="code_submit"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="code_cancel"),
    )

    return builder.as_markup()


def get_2fa_keyboard(current_password: str = "") -> InlineKeyboardMarkup:
    """Инлайн клавиатура для ввода 2FA пароля"""
    builder = InlineKeyboardBuilder()

    # Показываем маску пароля
    display = "*" * len(current_password) if current_password else "Введите пароль"
    builder.row(
        InlineKeyboardButton(text=display, callback_data="2fa_display")
    )

    # Буквы и цифры - основные символы
    builder.row(
        InlineKeyboardButton(text="1", callback_data="2fa_1"),
        InlineKeyboardButton(text="2", callback_data="2fa_2"),
        InlineKeyboardButton(text="3", callback_data="2fa_3"),
        InlineKeyboardButton(text="4", callback_data="2fa_4"),
        InlineKeyboardButton(text="5", callback_data="2fa_5"),
    )
    builder.row(
        InlineKeyboardButton(text="6", callback_data="2fa_6"),
        InlineKeyboardButton(text="7", callback_data="2fa_7"),
        InlineKeyboardButton(text="8", callback_data="2fa_8"),
        InlineKeyboardButton(text="9", callback_data="2fa_9"),
        InlineKeyboardButton(text="0", callback_data="2fa_0"),
    )
    builder.row(
        InlineKeyboardButton(text="a-z", callback_data="2fa_letters"),
        InlineKeyboardButton(text="A-Z", callback_data="2fa_LETTERS"),
        InlineKeyboardButton(text="!@#", callback_data="2fa_symbols"),
    )
    builder.row(
        InlineKeyboardButton(text="⌫", callback_data="2fa_backspace"),
        InlineKeyboardButton(text="✓ Подтвердить", callback_data="2fa_submit"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="2fa_cancel"),
    )

    return builder.as_markup()


def get_letters_keyboard(uppercase: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для ввода букв"""
    builder = InlineKeyboardBuilder()

    if uppercase:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        prefix = "2fa_upper_"
    else:
        letters = "abcdefghijklmnopqrstuvwxyz"
        prefix = "2fa_lower_"

    # 5 букв в ряд
    for i in range(0, len(letters), 5):
        row_letters = letters[i:i+5]
        builder.row(*[
            InlineKeyboardButton(text=letter, callback_data=f"{prefix}{letter}")
            for letter in row_letters
        ])

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="2fa_back_to_main"),
    )

    return builder.as_markup()


def get_symbols_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ввода символов"""
    builder = InlineKeyboardBuilder()

    symbols = "!@#$%^&*()-_=+[]{}|;:',.<>?/`~"

    # 6 символов в ряд
    for i in range(0, len(symbols), 6):
        row_symbols = symbols[i:i+6]
        builder.row(*[
            InlineKeyboardButton(text=sym, callback_data=f"2fa_sym_{sym}")
            for sym in row_symbols
        ])

    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="2fa_back_to_main"),
    )

    return builder.as_markup()
