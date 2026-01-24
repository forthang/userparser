import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from bot.config import config
from bot.database.connection import init_db, async_session
from bot.database.crud import UserCRUD
from bot.services.scheduler import get_scheduler
from bot.handlers import start, groups, keywords, cities, monitoring, subscription, admin
from bot.handlers.monitoring import process_group_message, set_bot_instance
from userbot.client import userbot_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    logger.info("Bot starting...")

    await init_db()
    logger.info("Database initialized")

    # Устанавливаем инстанс бота для monitoring handler
    set_bot_instance(bot)

    scheduler = get_scheduler(bot)
    await scheduler.start()
    logger.info("Scheduler started")

    await start_active_userbots(bot)
    logger.info("Active userbots started")


async def on_shutdown(bot: Bot):
    logger.info("Bot shutting down...")

    scheduler = get_scheduler(bot)
    await scheduler.stop()

    await userbot_pool.stop_all()

    logger.info("Bot shutdown complete")


async def start_active_userbots(bot: Bot):
    async with async_session() as session:
        active_users = await UserCRUD.get_active_users_with_monitoring(session)

        logger.info(f"Found {len(active_users)} users with active monitoring")

        for user in active_users:
            try:
                async def message_callback(
                    user_tg_id: int,
                    group_id: int,
                    group_name: str,
                    message_id: int,
                    message_text: str,
                    pyrogram_message=None,
                ):
                    await process_group_message(
                        bot=bot,
                        user_telegram_id=user_tg_id,
                        group_id=group_id,
                        group_name=group_name,
                        message_id=message_id,
                        message_text=message_text,
                    )

                success = await userbot_pool.start_client(
                    user_db_id=user.id,
                    user_telegram_id=user.telegram_id,
                    session_string=user.session_string,
                    on_message_callback=message_callback,
                )

                if success:
                    logger.info(f"Started userbot for user {user.telegram_id}")
                else:
                    logger.warning(
                        f"Failed to start userbot for user {user.telegram_id}"
                    )

            except Exception as e:
                logger.error(
                    f"Error starting userbot for user {user.telegram_id}: {e}"
                )


async def main():
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(groups.router)
    dp.include_router(keywords.router)
    dp.include_router(cities.router)
    dp.include_router(monitoring.router)
    dp.include_router(subscription.router)
    dp.include_router(admin.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot polling...")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
