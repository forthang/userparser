import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, PaymentCRUD
from bot.keyboards.main_menu import MainMenuText, get_main_menu
from bot.keyboards.inline import get_subscription_keyboard
from bot.services.payment import YukassaPayment, payment_manager
from bot.config import config

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text == MainMenuText.SUBSCRIPTION)
async def subscription_menu(message: Message):
    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        if user.is_subscription_active:
            days_left = (user.subscription_end - datetime.utcnow()).days
            text = (
                f"💳 <b>Ваша подписка</b>\n\n"
                f"✅ Статус: Активна\n"
                f"📅 Действует до: {user.subscription_end.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏳ Осталось дней: {days_left}\n\n"
                f"💰 Стоимость продления: {config.subscription.price} руб.\n"
                f"📆 Срок: {config.subscription.days} дней"
            )
            has_subscription = True
        else:
            text = (
                f"💳 <b>Подписка</b>\n\n"
                f"❌ Статус: Не активна\n\n"
                f"Для использования мониторинга необходимо оформить подписку.\n\n"
                f"💰 Стоимость: {config.subscription.price} руб.\n"
                f"📆 Срок: {config.subscription.days} дней\n\n"
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
    """Временно отключена оплата - сразу активируем подписку"""
    await callback.answer("⏳ Активирую подписку...")

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

        if not user:
            await callback.message.answer("Ошибка. Нажмите /start")
            return

        # Временно: сразу активируем подписку без оплаты
        await UserCRUD.update_subscription(
            session,
            user.id,
            config.subscription.days,
        )

        await callback.message.edit_text(
            f"✅ <b>Подписка активирована!</b>\n\n"
            f"Срок: {config.subscription.days} дней\n\n"
            f"Теперь вы можете использовать все функции бота.",
            parse_mode="HTML",
        )

        user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
        await callback.message.answer(
            "Главное меню:",
            reply_markup=get_main_menu(user.monitoring_enabled),
        )


@router.callback_query(F.data == "sub_extend")
async def subscription_extend(callback: CallbackQuery):
    await subscription_buy(callback)


@router.callback_query(F.data.startswith("sub_check:"))
async def subscription_check(callback: CallbackQuery):
    payment_id = callback.data.split(":")[1]

    await callback.answer("⏳ Проверяю оплату...")

    payment_data = await YukassaPayment.check_payment(payment_id)

    if not payment_data:
        await callback.message.answer(
            "❌ Не удалось проверить платёж.\n"
            "Попробуйте ещё раз или обратитесь в поддержку."
        )
        return

    if YukassaPayment.is_payment_successful(payment_data["status"]):
        async with async_session() as session:
            user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)

            if user:
                await UserCRUD.update_subscription(
                    session,
                    user.id,
                    config.subscription.days,
                )

                await PaymentCRUD.confirm_payment(session, payment_id)

                payment_manager.remove_pending(user.id)

                await callback.message.edit_text(
                    f"✅ <b>Оплата успешна!</b>\n\n"
                    f"Ваша подписка активирована на {config.subscription.days} дней.\n"
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
