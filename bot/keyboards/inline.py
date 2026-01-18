from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Keyword, City


def get_keywords_keyboard(keywords: List[Keyword]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    sorted_keywords = sorted(keywords, key=lambda k: (not k.is_default, k.word.lower()))

    for kw in sorted_keywords[:15]:
        prefix = "📌" if kw.is_default else "📝"
        text = f"{prefix} {kw.word}"
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"kw_info:{kw.id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"kw_delete:{kw.id}",
            ),
        )

    if len(keywords) > 15:
        builder.row(
            InlineKeyboardButton(
                text=f"... ещё {len(keywords) - 15} слов",
                callback_data="kw_show_all",
            )
        )

    builder.row(
        InlineKeyboardButton(text="➕ Добавить слово", callback_data="kw_add"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Сбросить к стандартным", callback_data="kw_reset"),
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


def get_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📩 Откликнуться",
            callback_data=f"order_respond:{order_id}",
        )
    )
    return builder.as_markup()


def get_order_responded_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Вы откликнулись", callback_data="noop")
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
