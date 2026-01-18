from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Group


GROUPS_PER_PAGE = 8


def get_groups_keyboard(
    groups: List[Group],
    page: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    sorted_groups = sorted(groups, key=lambda g: (not g.is_enabled, g.group_name.lower()))

    total_pages = (len(sorted_groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE
    start_idx = page * GROUPS_PER_PAGE
    end_idx = start_idx + GROUPS_PER_PAGE
    page_groups = sorted_groups[start_idx:end_idx]

    for group in page_groups:
        if group.is_enabled:
            status = "✅"
        else:
            status = "⬜"

        name = group.group_name[:30] + "..." if len(group.group_name) > 30 else group.group_name
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"group_toggle:{group.id}",
            )
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"groups_page:{page-1}")
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"groups_page:{page+1}")
        )

    if nav_buttons:
        builder.row(*nav_buttons)

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
