import asyncio
import logging
from typing import Dict, Set, Callable, Awaitable, Union
from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from pyrogram.enums import ChatType

from bot.config import config
from bot.database.connection import async_session
from bot.database.crud import UserCRUD, GroupCRUD

logger = logging.getLogger(__name__)


class UserBotClient:
    def __init__(
        self,
        user_db_id: int,
        user_telegram_id: int,
        session_string: str,
        on_message_callback: Callable[[int, int, str, int, str, Message], Awaitable[None]],
    ):
        self.user_db_id = user_db_id
        self.user_telegram_id = user_telegram_id
        self.session_string = session_string
        self.on_message_callback = on_message_callback

        self.client = Client(
            name=f"userbot_{user_db_id}",
            api_id=config.telegram_api.api_id,
            api_hash=config.telegram_api.api_hash,
            session_string=session_string,
            in_memory=True,
        )

        self.monitored_groups: Set[int] = set()
        self._running = False

    async def start(self):
        if self._running:
            return

        await self._load_monitored_groups()

        self.client.add_handler(
            MessageHandler(self._handle_message)
        )

        await self.client.start()
        self._running = True
        logger.info(f"UserBot started for user {self.user_telegram_id}")

    async def stop(self):
        if not self._running:
            return

        self._running = False
        await self.client.stop()
        logger.info(f"UserBot stopped for user {self.user_telegram_id}")

    async def _load_monitored_groups(self):
        async with async_session() as session:
            groups = await GroupCRUD.get_enabled_groups(session, self.user_db_id)
            self.monitored_groups = {g.telegram_group_id for g in groups}

        logger.info(
            f"Loaded {len(self.monitored_groups)} monitored groups "
            f"for user {self.user_telegram_id}"
        )

    async def refresh_groups(self):
        await self._load_monitored_groups()

    async def _handle_message(self, client: Client, message: Message):
        try:
            if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                return

            if message.chat.id not in self.monitored_groups:
                return

            if message.from_user and message.from_user.id == self.user_telegram_id:
                return

            if not message.text:
                return

            await self.on_message_callback(
                self.user_telegram_id,
                message.chat.id,
                message.chat.title or "Unknown",
                message.id,
                message.text,
                message,
            )

        except Exception as e:
            logger.error(f"Error handling message: {e}")


class UserBotPool:
    _instance = None
    _clients: Dict[int, UserBotClient] = {}
    _lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "UserBotPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_client(
        self,
        user_db_id: int,
        user_telegram_id: int,
        session_string: str,
        on_message_callback: Callable,
    ) -> bool:
        async with self._lock:
            if user_db_id in self._clients:
                return True

            try:
                client = UserBotClient(
                    user_db_id=user_db_id,
                    user_telegram_id=user_telegram_id,
                    session_string=session_string,
                    on_message_callback=on_message_callback,
                )
                await client.start()
                self._clients[user_db_id] = client
                return True

            except Exception as e:
                logger.error(
                    f"Error starting userbot for user {user_telegram_id}: {e}"
                )
                return False

    async def stop_client(self, user_db_id: int):
        async with self._lock:
            if user_db_id in self._clients:
                await self._clients[user_db_id].stop()
                del self._clients[user_db_id]

    async def stop_all(self):
        async with self._lock:
            for user_db_id in list(self._clients.keys()):
                await self._clients[user_db_id].stop()
            self._clients.clear()

    def is_running(self, user_db_id: int) -> bool:
        return user_db_id in self._clients

    async def refresh_groups(self, user_db_id: int):
        if user_db_id in self._clients:
            await self._clients[user_db_id].refresh_groups()

    def get_active_count(self) -> int:
        return len(self._clients)


userbot_pool = UserBotPool.get_instance()
