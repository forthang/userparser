import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, PaymentCRUD, BotSettingsCRUD
from bot.keyboards.main_menu import MainMenuText, get_main_menu
from bot.keyboards.inline import get_subscription_keyboard
from bot.services.payment import (
    PaymentService,
    PaymentSystem,
    YukassaPayment,
    payment_manager,
)
from bot.config import config

logger = logging.getLogger(__name__)

router = Router()


async def get_payment_settings(session) -> dict:
    """Получает настройки платежей из БД"""
    system_str = await BotSettingsCRUD.get(session, "payment_system", "yukassa")
    price_str = await BotSettingsCRUD.get(session, "subscription_price", str(config.subscription.price))
    days_str = await BotSettingsCRUD.get(session, "subscription_days", str(config.subscription.days))

    try:
        system = PaymentSystem(system_str)
    except ValueError:
        system = PaymentSystem.YUKASSA

    return {
        "system": system,
        "price": int(price_str),
        "days": int(days_str),
    }


@router.message(F.text == MainMenuText.SUBSCRIPTION)
async def subscription_menu(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        settings = await get_payment_settings(session)

        if user.is_subscription_active:
            days_left = (user.subscription_end - datetime.utcnow()).days
            text = (
                f"💳 <b>Ваша подписка</b>\n\n"
                f"✅ Статус: Активна\n"
                f"📅 Действует до: {user.subscription_end.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏳ Осталось дней: {days_left}\n\n"
                f"💰 Стоимость продления: {settings['price']} руб.\n"
                f"📆 Срок: {settings['days']} дней"
            )
            has_subscription = True
        else:
            text = (
                f"💳 <b>Подписка</b>\n\n"
                f"❌ Статус: Не активна\n\n"
                f"Для использования мониторинга необходимо оформить подписку.\n\n"
                f"💰 Стоимость: {settings['price']} руб.\n"
                f"📆 Срок: {settings['days']} дней\n\n"
                f"После оплаты вы сможете:\n"
                f"• Мониторить неограниченное количество групп\n"
                f"• Получать уведомления о заказах\n"
                f"• Откликаться на заказы в один клик"
            )
            has_subscription = False

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(has_subscription),
        )


@router.callback_query(F.data == "sub_buy")
async def subscription_buy(callback: CallbackQuery):
    """Создание платежа для покупки подписки"""
    await callback.answer("⏳ Создаю платеж...")

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.message.answer("Ошибка. Нажмите /start")
            return

        settings = await get_payment_settings(session)

        # Проверяем, что платежная система не отключена
        if settings["system"] == PaymentSystem.DISABLED:
            await callback.message.edit_text(
                "⚠️ <b>Оплата временно недоступна</b>\n\n"
                "Платежная система не настроена.\n"
                "Обратитесь к администратору.",
                parse_mode="HTML",
            )
            return

        # Создаем запись о платеже в БД
        db_payment = await PaymentCRUD.create_payment(
            session,
            user_id=user.id,
            amount=settings["price"],
            payment_id="pending",  # Обновим после создания платежа
        )

        # Создаем платеж через платежную систему
        payment_result = await PaymentService.create_payment(
            system=settings["system"],
            amount=settings["price"],
            user_id=callback.from_user.id,
            invoice_id=db_payment.id,
            description=f"Подписка на {settings['days']} дней",
        )

        if not payment_result:
            await callback.message.edit_text(
                "❌ <b>Ошибка создания платежа</b>\n\n"
                "Попробуйте позже или обратитесь в поддержку.",
                parse_mode="HTML",
            )
            return

        # Обновляем payment_id в БД
        db_payment.payment_id = payment_result["payment_id"]
        await session.commit()

        # Сохраняем информацию о платеже
        payment_manager.add_pending(
            user_id=user.id,
            payment_id=payment_result["payment_id"],
            system=settings["system"],
            db_payment_id=db_payment.id,
        )

        # Формируем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="💳 Оплатить",
                url=payment_result["payment_url"]
            )
        )
        builder.row(
            InlineKeyboardButton(text="❌ Отмена", callback_data="sub_cancel")
        )

        system_names = {
            PaymentSystem.YUKASSA: "ЮКасса",
            PaymentSystem.ROBOKASSA: "Робокасса",
            PaymentSystem.TINKOFF: "Тинькофф",
        }

        await callback.message.edit_text(
            f"💳 <b>Оплата подписки</b>\n\n"
            f"💰 Сумма: <b>{settings['price']} руб.</b>\n"
            f"📆 Срок: <b>{settings['days']} дней</b>\n"
            f"🏦 Система: {system_names.get(settings['system'], 'Неизвестно')}\n\n"
            f"Нажмите кнопку «Оплатить» для перехода на страницу оплаты.\n\n"
            f"<i>После оплаты подписка активируется автоматически</i>",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )


@router.callback_query(F.data == "sub_extend")
async def subscription_extend(callback: CallbackQuery):
    await subscription_buy(callback)


@router.callback_query(F.data.startswith("sub_check:"))
async def subscription_check(callback: CallbackQuery):
    payment_id = callback.data.split(":")[1]

    await callback.answer("⏳ Проверяю оплату...")

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.message.answer("Ошибка. Нажмите /start")
            return

        settings = await get_payment_settings(session)

        # Проверяем статус платежа
        payment_data = await PaymentService.check_payment(
            system=settings["system"],
            payment_id=payment_id,
        )

        if not payment_data:
            await callback.message.answer(
                "❌ Не удалось проверить платёж.\n"
                "Попробуйте ещё раз или обратитесь в поддержку."
            )
            return

        if PaymentService.is_payment_successful(settings["system"], payment_data["status"]):
            # Активируем подписку
            await UserCRUD.update_subscription(
                session,
                user.id,
                settings["days"],
            )

            # Подтверждаем платеж
            await PaymentCRUD.confirm_payment(session, payment_id)

            # Удаляем из ожидающих
            payment_manager.remove_pending(user.id)

            await callback.message.edit_text(
                f"✅ <b>Оплата успешна!</b>\n\n"
                f"Ваша подписка активирована на {settings['days']} дней.\n"
                f"Теперь вы можете использовать все функции бота.",
                parse_mode="HTML",
            )

            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
            await callback.message.answer(
                "Главное меню:",
                reply_markup=get_main_menu(user.monitoring_enabled),
            )

        elif payment_data["status"] == "pending":
            await callback.message.answer(
                "⏳ Платёж ещё обрабатывается.\n"
                "Подождите немного и попробуйте снова."
            )
        elif payment_data["status"] == "canceled":
            await callback.message.edit_text(
                "❌ Платёж был отменён.\n"
                "Вы можете создать новый платёж.",
            )
            payment_manager.remove_pending(callback.from_user.id)
        else:
            await callback.message.answer(
                f"⚠️ Статус платежа: {payment_data['status']}\n"
                "Если вы оплатили, но подписка не активировалась,\n"
                "обратитесь в поддержку."
            )


@router.callback_query(F.data == "sub_cancel")
async def subscription_cancel(callback: CallbackQuery):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        if user:
            payment_manager.remove_pending(user.id)

    await callback.message.edit_text("❌ Оплата отменена.")
    await callback.answer()


@router.callback_query(F.data == "sub_video")
async def subscription_video(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "📹 <b>Видео инструкция</b>\n\n"
        "Здесь будет ссылка на видео инструкцию по использованию бота.\n\n"
        "(Добавьте ссылку на видео в настройках бота)",
        parse_mode="HTML",
    )
