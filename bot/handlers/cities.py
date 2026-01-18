from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, CityCRUD
from bot.keyboards.main_menu import MainMenuText, get_cancel_keyboard, get_main_menu
from bot.keyboards.inline import (
    get_cities_keyboard,
    get_city_confirm_delete,
    get_city_confirm_delete_all,
)
from bot.utils.cities_data import get_city_variations, CITIES_DATA

router = Router()


class CityStates(StatesGroup):
    waiting_city = State()
    confirm_delete = State()


@router.message(F.text == MainMenuText.CITIES)
async def cities_menu(message: Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        cities = await CityCRUD.get_user_cities(session, user.id)

        available_cities = ", ".join(list(CITIES_DATA.keys())[:5]) + "..."

        await message.answer(
            f"🏙 <b>Города</b>\n\n"
            f"Добавлено городов: {len(cities)}\n\n"
            f"При добавлении города автоматически добавляются:\n"
            f"• Все склонения названия\n"
            f"• Пригороды и районы\n\n"
            f"Доступные города с данными: {available_cities}",
            parse_mode="HTML",
            reply_markup=get_cities_keyboard(cities),
        )


@router.callback_query(F.data == "city_add")
async def city_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CityStates.waiting_city)
    await callback.message.answer(
        "🏙 Введите название города:\n"
        "(например: Москва, Санкт-Петербург, Казань)",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(CityStates.waiting_city)
async def city_add_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
            cities = await CityCRUD.get_user_cities(session, user.id)
            await message.answer(
                "Отменено.",
                reply_markup=get_main_menu(user.monitoring_enabled if user else False),
            )
            await message.answer(
                "🏙 <b>Города</b>",
                parse_mode="HTML",
                reply_markup=get_cities_keyboard(cities),
            )
        return

    city_name = message.text.strip()

    if len(city_name) < 2:
        await message.answer(
            "❌ Название слишком короткое.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    if len(city_name) > 100:
        await message.answer(
            "❌ Название слишком длинное.",
            reply_markup=get_cancel_keyboard(),
        )
        return

    variations = get_city_variations(city_name)

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            await state.clear()
            return

        existing = await CityCRUD.get_user_cities(session, user.id)
        if any(c.city_name.lower() == city_name.lower() for c in existing):
            await message.answer(
                "⚠️ Этот город уже добавлен.",
                reply_markup=get_cancel_keyboard(),
            )
            return

        await CityCRUD.add_city(session, user.id, city_name.title(), variations)

        await state.clear()

        cities = await CityCRUD.get_user_cities(session, user.id)

        sample_variations = variations[:5]
        variations_text = ", ".join(sample_variations)
        if len(variations) > 5:
            variations_text += f" и ещё {len(variations) - 5}..."

        await message.answer(
            f"✅ Город «{city_name.title()}» добавлен!\n\n"
            f"Вариации для поиска ({len(variations)}):\n"
            f"{variations_text}",
            reply_markup=get_main_menu(user.monitoring_enabled),
        )
        await message.answer(
            "🏙 <b>Города</b>",
            parse_mode="HTML",
            reply_markup=get_cities_keyboard(cities),
        )


@router.callback_query(F.data.startswith("city_info:"))
async def city_info(callback: CallbackQuery):
    city_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        from sqlalchemy import select
        from bot.database.models import City

        result = await session.execute(select(City).where(City.id == city_id))
        city = result.scalar_one_or_none()

        if city:
            variations = city.variations or []
            variations_text = ", ".join(variations[:10])
            if len(variations) > 10:
                variations_text += f"\n... и ещё {len(variations) - 10}"

            await callback.answer()
            await callback.message.answer(
                f"🏙 <b>{city.city_name}</b>\n\n"
                f"Вариации для поиска ({len(variations)}):\n"
                f"{variations_text}",
                parse_mode="HTML",
            )
        else:
            await callback.answer("Город не найден")


@router.callback_query(F.data.startswith("city_delete:"))
async def city_delete(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split(":")[1])
    await state.update_data(delete_city_id=city_id)

    await callback.message.edit_text(
        "⚠️ Удалить этот город?",
        reply_markup=get_city_confirm_delete(),
    )


@router.callback_query(F.data == "city_confirm_delete")
async def city_confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    city_id = data.get("delete_city_id")

    if not city_id:
        await callback.answer("Ошибка")
        return

    async with async_session() as session:
        await CityCRUD.delete_city(session, city_id)

        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        cities = await CityCRUD.get_user_cities(session, user.id)

    await state.clear()
    await callback.answer("✅ Город удалён")

    await callback.message.edit_text(
        "🏙 <b>Города</b>",
        parse_mode="HTML",
        reply_markup=get_cities_keyboard(cities),
    )


@router.callback_query(F.data == "city_delete_all")
async def city_delete_all_ask(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы уверены, что хотите удалить ВСЕ города?",
        parse_mode="HTML",
        reply_markup=get_city_confirm_delete_all(),
    )


@router.callback_query(F.data == "city_confirm_delete_all")
async def city_confirm_delete_all(callback: CallbackQuery):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.answer("Ошибка")
            return

        await CityCRUD.delete_all_cities(session, user.id)

        cities = await CityCRUD.get_user_cities(session, user.id)

    await callback.answer("✅ Все города удалены")

    await callback.message.edit_text(
        "🏙 <b>Города</b>\n\n"
        "Список пуст. Добавьте города для фильтрации заказов.",
        parse_mode="HTML",
        reply_markup=get_cities_keyboard(cities),
    )


@router.callback_query(F.data == "city_cancel")
async def city_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        cities = await CityCRUD.get_user_cities(session, user.id)

    await callback.message.edit_text(
        "🏙 <b>Города</b>",
        parse_mode="HTML",
        reply_markup=get_cities_keyboard(cities),
    )
