from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Keyword, City


KEYWORDS_PER_PAGE = 10


def get_keywords_keyboard(
    keywords: List[Keyword],
    page: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    sorted_keywords = sorted(keywords, key=lambda k: (not k.is_default, k.word.lower()))

    total_pages = max(1, (len(sorted_keywords) + KEYWORDS_PER_PAGE - 1) // KEYWORDS_PER_PAGE)
    page = min(page, total_pages - 1)
    start_idx = page * KEYWORDS_PER_PAGE
    end_idx = start_idx + KEYWORDS_PER_PAGE
    page_keywords = sorted_keywords[start_idx:end_idx]

    for kw in page_keywords:
        prefix = "📌" if kw.is_default else "📝"
        word_display = kw.word[:25] + "..." if len(kw.word) > 25 else kw.word
        text = f"{prefix} {word_display}"
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"kw_info:{kw.id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"kw_delete:{kw.id}:{page}",
            ),
        )

    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"kw_page:{page-1}")
        )

    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )

    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"kw_page:{page+1}")
        )

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="➕ Добавить слово", callback_data="kw_add"),
        InlineKeyboardButton(text="📝 Добавить списком", callback_data="kw_bulk_add"),
    )
    builder.row(
        InlineKeyboardButton(text="🧹 Удалить все", callback_data="kw_delete_all"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"),
    )

    return builder.as_markup()


def get_keyword_confirm_delete() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="kw_confirm_delete"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="kw_cancel"),
    )
    return builder.as_markup()


def get_keyword_confirm_delete_all() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить все", callback_data="kw_confirm_delete_all"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="kw_cancel"),
    )
    return builder.as_markup()


def get_keyword_confirm_reset() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, сбросить", callback_data="kw_confirm_reset"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="kw_cancel"),
    )
    return builder.as_markup()


def get_cities_keyboard(cities: List[City]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for city in cities[:10]:
        name = city.city_name[:25] + "..." if len(city.city_name) > 25 else city.city_name
        variations_count = len(city.variations) if city.variations else 0
        builder.row(
            InlineKeyboardButton(
                text=f"🏙 {name} ({variations_count} вариаций)",
                callback_data=f"city_info:{city.id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"city_delete:{city.id}",
            ),
        )

    builder.row(
        InlineKeyboardButton(text="➕ Добавить город", callback_data="city_add"),
    )
    builder.row(
        InlineKeyboardButton(text="🧹 Удалить все города", callback_data="city_delete_all"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"),
    )

    return builder.as_markup()


def get_city_confirm_delete() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="city_confirm_delete"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="city_cancel"),
    )
    return builder.as_markup()


def get_city_confirm_delete_all() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить все", callback_data="city_confirm_delete_all"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="city_cancel"),
    )
    return builder.as_markup()


def get_subscription_keyboard(has_subscription: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if has_subscription:
        builder.row(
            InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="sub_extend"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="💳 Купить подписку", callback_data="sub_buy"),
        )

    builder.row(
        InlineKeyboardButton(text="📹 Видео инструкция", callback_data="sub_video"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"),
    )

    return builder.as_markup()


def get_order_keyboard(order_id: int, group_id: int, message_id: int) -> InlineKeyboardMarkup:
    """Клавиатура заказа: кнопка взять заказ + перейти в группу на одной строке"""
    builder = InlineKeyboardBuilder()

    # Формируем ссылку на сообщение в группе
    # Для приватных групп формат: t.me/c/{channel_id}/{message_id}
    # channel_id = group_id без префикса -100
    channel_id = str(group_id).replace("-100", "")
    group_link = f"https://t.me/c/{channel_id}/{message_id}"

    # Обе кнопки на одной строке
    builder.row(
        InlineKeyboardButton(
            text="✅ Откликнуться",
            callback_data=f"order_take:{order_id}",
        ),
        InlineKeyboardButton(
            text="🔗 В группу",
            url=group_link
        ),
    )
    return builder.as_markup()


def get_order_taken_keyboard(group_id: int, message_id: int) -> InlineKeyboardMarkup:
    """Клавиатура после взятия заказа с кнопкой перехода в группу"""
    builder = InlineKeyboardBuilder()

    # Формируем ссылку на сообщение в группе
    # Для приватных групп формат: t.me/c/{channel_id}/{message_id}
    # channel_id = group_id без префикса -100
    channel_id = str(group_id).replace("-100", "")
    group_link = f"https://t.me/c/{channel_id}/{message_id}"

    # Обе кнопки на одной строке
    builder.row(
        InlineKeyboardButton(
            text="✅ Заказ взят",
            callback_data="noop"
        ),
        InlineKeyboardButton(
            text="🔗 В группу",
            url=group_link
        ),
    )
    return builder.as_markup()


def get_monitoring_status_keyboard(is_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_enabled:
        builder.row(
            InlineKeyboardButton(text="⏹ Остановить", callback_data="monitoring_stop")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="▶️ Запустить", callback_data="monitoring_start")
        )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")
    )
    return builder.as_markup()
