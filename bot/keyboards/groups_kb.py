from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Group


GROUPS_PER_PAGE = 8


def get_groups_keyboard(
    groups: List[Group],
    page: int = 0,
    search_query: Optional[str] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Фильтруем по поиску если есть
    if search_query:
        filtered_groups = [g for g in groups if search_query.lower() in g.group_name.lower()]
    else:
        filtered_groups = groups

    sorted_groups = sorted(filtered_groups, key=lambda g: (not g.is_enabled, g.group_name.lower()))

    total_pages = max(1, (len(sorted_groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    # Корректируем страницу если вышли за пределы
    page = min(page, total_pages - 1)
    start_idx = page * GROUPS_PER_PAGE
    end_idx = start_idx + GROUPS_PER_PAGE
    page_groups = sorted_groups[start_idx:end_idx]

    if search_query:
        builder.row(
            InlineKeyboardButton(
                text=f"🔍 Поиск: {search_query[:15]}{'...' if len(search_query) > 15 else ''} ❌",
                callback_data="groups_clear_search",
            )
        )

    for group in page_groups:
        if group.is_enabled:
            status = "✅"
        else:
            status = "⬜"

        name = group.group_name[:30] + "..." if len(group.group_name) > 30 else group.group_name
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"group_toggle:{group.id}:{page}",
            )
        )

    if not page_groups and search_query:
        builder.row(
            InlineKeyboardButton(text="Ничего не найдено", callback_data="noop")
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"groups_page:{page-1}")
        )

    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )

    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"groups_page:{page+1}")
        )

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="🔍 Поиск", callback_data="groups_search"),
        InlineKeyboardButton(text="📝 Выбрать списком", callback_data="groups_bulk_enable"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="groups_refresh")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")
    )

    return builder.as_markup()


def get_groups_empty_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Загрузить группы", callback_data="groups_refresh")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")
    )
    return builder.as_markup()
