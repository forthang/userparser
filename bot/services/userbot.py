import logging
import asyncio
from typing import Dict, List, Optional, Any
from pyrogram import Client
from pyrogram.types import Chat
from pyrogram.enums import ChatType

logger = logging.getLogger(__name__)


# Глобальное хранилище клиентов для авторизации
_auth_clients: Dict[int, Client] = {}


class UserBotService:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: Optional[str] = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self._client: Optional[Client] = None

    async def _get_client(self) -> Client:
        if self._client is None:
            if self.session_string:
                self._client = Client(
                    name="userbot",
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    session_string=self.session_string,
                    in_memory=True,
                )
            else:
                self._client = Client(
                    name="userbot",
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    in_memory=True,
                )
        return self._client

    @classmethod
    async def send_code(cls, api_id: int, api_hash: str, phone: str, user_id: int) -> str:
        """Отправляет код и сохраняет клиент для последующего sign_in"""
        # Закрываем старый клиент если был
        if user_id in _auth_clients:
            try:
                old_client = _auth_clients[user_id]
                if old_client.is_connected:
                    await old_client.disconnect()
            except:
                pass

        # Создаём новый клиент
        client = Client(
            name=f"auth_{user_id}",
            api_id=api_id,
            api_hash=api_hash,
            in_memory=True,
        )

        await client.connect()
        sent_code = await client.send_code(phone)

        # Сохраняем клиент глобально
        _auth_clients[user_id] = client

        logger.info(f"Code sent to {phone}, phone_code_hash: {sent_code.phone_code_hash[:10]}...")
        return sent_code.phone_code_hash

    @classmethod
    async def sign_in(
        cls,
        user_id: int,
        phone: str,
        code: str,
        phone_code_hash: str,
    ) -> Dict[str, Any]:
        """Авторизуется используя сохранённый клиент"""
        if user_id not in _auth_clients:
            raise Exception("Сначала запросите код авторизации")

        client = _auth_clients[user_id]

        if not client.is_connected:
            await client.connect()

        try:
            await client.sign_in(
                phone_number=phone,
                phone_code_hash=phone_code_hash,
                phone_code=code,
            )

            session_string = await client.export_session_string()

            # Очищаем после успешной авторизации
            try:
                await client.disconnect()
            except:
                pass
            del _auth_clients[user_id]

            return {
                "success": True,
                "session_string": session_string,
                "need_2fa": False,
            }

        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "2fa" in error_str or "two-step" in error_str:
                # Не удаляем клиент - нужен для 2FA
                return {
                    "success": False,
                    "need_2fa": True,
                }
            # При другой ошибке очищаем
            try:
                await client.disconnect()
            except:
                pass
            if user_id in _auth_clients:
                del _auth_clients[user_id]
            raise

    @classmethod
    async def check_password(cls, user_id: int, password: str) -> str:
        """Проверяет 2FA пароль"""
        if user_id not in _auth_clients:
            raise Exception("Сессия авторизации истекла. Начните заново.")

        client = _auth_clients[user_id]

        if not client.is_connected:
            await client.connect()

        await client.check_password(password)
        session_string = await client.export_session_string()

        # Очищаем после успешной авторизации
        try:
            await client.disconnect()
        except:
            pass
        del _auth_clients[user_id]

        return session_string

    @classmethod
    def cleanup_auth(cls, user_id: int):
        """Очищает сессию авторизации"""
        if user_id in _auth_clients:
            try:
                client = _auth_clients[user_id]
                if client.is_connected:
                    asyncio.create_task(client.disconnect())
            except:
                pass
            del _auth_clients[user_id]

    async def get_dialogs(self) -> List[Dict[str, Any]]:
        client = await self._get_client()

        try:
            await client.start()

            groups = []
            async for dialog in client.get_dialogs():
                chat: Chat = dialog.chat

                if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    groups.append({
                        "id": chat.id,
                        "name": chat.title or "Без названия",
                        "type": str(chat.type),
                        "members_count": getattr(chat, "members_count", None),
                    })

            await client.stop()
            return groups

        except Exception as e:
            logger.error(f"Error getting dialogs: {e}")
            try:
                await client.stop()
            except:
                pass
            raise

    async def send_reply(
        self,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> bool:
        client = await self._get_client()

        try:
            await client.start()

            await client.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=message_id,
            )

            await client.stop()
            return True

        except Exception as e:
            logger.error(f"Error sending reply: {e}")
            try:
                await client.stop()
            except:
                pass
            raise

    async def is_session_valid(self) -> bool:
        if not self.session_string:
            return False

        client = await self._get_client()

        try:
            await client.start()
            me = await client.get_me()
            await client.stop()
            return me is not None

        except Exception as e:
            logger.error(f"Session validation error: {e}")
            try:
                await client.stop()
            except:
                pass
            return False


class UserBotManager:
    _instances: Dict[int, Client] = {}

    @classmethod
    async def get_client(
        cls,
        user_id: int,
        api_id: int,
        api_hash: str,
        session_string: str,
    ) -> Client:
        if user_id not in cls._instances:
            client = Client(
                name=f"userbot_{user_id}",
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                in_memory=True,
            )
            cls._instances[user_id] = client

        return cls._instances[user_id]

    @classmethod
    async def start_client(cls, user_id: int) -> bool:
        if user_id in cls._instances:
            client = cls._instances[user_id]
            if not client.is_connected:
                await client.start()
            return True
        return False

    @classmethod
    async def stop_client(cls, user_id: int) -> None:
        if user_id in cls._instances:
            client = cls._instances[user_id]
            try:
                if client.is_connected:
                    await client.stop()
            except:
                pass
            del cls._instances[user_id]

    @classmethod
    async def stop_all(cls) -> None:
        for user_id in list(cls._instances.keys()):
            await cls.stop_client(user_id)

    @classmethod
    def is_running(cls, user_id: int) -> bool:
        if user_id in cls._instances:
            return cls._instances[user_id].is_connected
        return False
