import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database.connection import async_session
from bot.database.crud import UserCRUD, UserLogCRUD

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("reply"))
async def cmd_reply(message: Message):
    """
    Handle /reply command - user replies to admin message.
    Usage: /reply <text>
    """
    # Get reply text (everything after /reply)
    text = message.text
    if text.startswith("/reply "):
        reply_text = text[7:].strip()
    elif text.startswith("/reply"):
        reply_text = text[6:].strip()
    else:
        reply_text = ""

    if not reply_text:
        await message.answer(
            "Используйте: /reply <ваш текст>\n"
            "Например: /reply Спасибо за помощь!"
        )
        return

    async with async_session() as session:
        user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)

        if not user:
            await message.answer("Ошибка. Нажмите /start")
            return

        # Log user reply
        await UserLogCRUD.add(
            session,
            user.id,
            "user_reply",
            reply_text[:500]  # Limit stored text
        )

    await message.answer(
        "Ваш ответ отправлен администратору."
    )

    logger.info(f"User {message.from_user.id} replied: {reply_text[:100]}...")
