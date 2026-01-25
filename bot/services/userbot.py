import logging
import os
import asyncio
import base64
from typing import Dict, List, Optional, Any
from pyrogram import Client
from pyrogram.types import Chat
from pyrogram.enums import ChatType
from pyrogram.raw import functions, types

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
            # Use consistent client parameters for all pyrogram clients
            client_params = {
                "api_id": self.api_id,
                "api_hash": self.api_hash,
                "app_version": "Telegram Android 10.0.0",
                "device_model": "Android 13",
                "system_version": "SDK 33",
                "lang_code": "en",
                "in_memory": True, # Userbots for monitoring can remain in memory
            }
            if self.session_string:
                self._client = Client(
                    name="userbot",
                    session_string=self.session_string,
                    **client_params
                )
            else:
                self._client = Client(
                    name="userbot",
                    **client_params
                )
        return self._client

    @classmethod
    async def send_code(cls, api_id: int, api_hash: str, phone: str, user_id: int) -> str:
        """Отправляет код и сохраняет клиент для последующего sign_in"""
        # Ensure any previous auth client is disconnected and removed
        cls.cleanup_auth(user_id)

        # Use consistent client parameters for all pyrogram clients
        client_params = {
            "api_id": api_id,
            "api_hash": api_hash,
            "app_version": "Telegram Android 10.0.0",
            "device_model": "Android 13",
            "system_version": "SDK 33",
            "lang_code": "en",
            # in_memory=False by default, so it will create a session file
        }

        # Создаём новый клиент для отправки кода
        client = Client(
            name=f"auth_{user_id}",
            **client_params
        )

        try:
            await client.connect()
            sent_code = await client.send_code(phone)
            logger.info(f"Code sent to {phone}, phone_code_hash: {sent_code.phone_code_hash[:10]}...")
            return sent_code.phone_code_hash
        finally:
            # Disconnect immediately after sending code, rely on session file for sign_in
            if client.is_connected:
                await client.disconnect()
            # Do NOT store client in _auth_clients, rely on session file
            # _auth_clients[user_id] = client # Removed

    @classmethod
    async def sign_in(
        cls,
        user_id: int,
        phone: str,
        code: str,
        phone_code_hash: str,
    ) -> Dict[str, Any]:
        """Авторизуется используя сохранённый клиент"""
        # Create a new client instance, which will load the session file created by send_code
        client = Client(
            name=f"auth_{user_id}",
            api_id=0, # These will be loaded from session file
            api_hash="", # These will be loaded from session file
            app_version="Telegram Android 10.0.0",
            device_model="Android 13",
            system_version="SDK 33",
            lang_code="en",
        )

        try:
            await client.connect() # Connects and loads session from file
            await client.sign_in(
                phone_number=phone,
                phone_code_hash=phone_code_hash,
                phone_code=code,
            )

            session_string = await client.export_session_string()

            return {
                "success": True,
                "session_string": session_string,
                "need_2fa": False,
            }

        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "2fa" in error_str or "two-step" in error_str:
                return {
                    "success": False,
                    "need_2fa": True,
                }
            raise # Re-raise other exceptions
        finally:
            # Always disconnect and clean up session file
            if client.is_connected:
                await client.disconnect()
            try:
                os.remove(f"auth_{user_id}.session")
            except FileNotFoundError:
                pass

    @classmethod
    async def check_password(cls, user_id: int, password: str) -> str:
        """Проверяет 2FA пароль"""
        # Create a new client instance, which will load the session file
        client = Client(
            name=f"auth_{user_id}",
            api_id=0, # These will be loaded from session file
            api_hash="", # These will be loaded from session file
            app_version="Telegram Android 10.0.0",
            device_model="Android 13",
            system_version="SDK 33",
            lang_code="en",
        )

        try:
            await client.connect() # Connects and loads session from file
            await client.check_password(password)
            session_string = await client.export_session_string()
            return session_string
        finally:
            # Always disconnect and clean up session file
            if client.is_connected:
                await client.disconnect()
            try:
                os.remove(f"auth_{user_id}.session")
            except FileNotFoundError:
                pass

    @classmethod
    def cleanup_auth(cls, user_id: int):
        """Очищает сессию авторизации"""
        # Disconnect any client that might still be in _auth_clients (legacy or error state)
        if user_id in _auth_clients:
            try:
                client = _auth_clients[user_id]
                if client.is_connected:
                    asyncio.create_task(client.disconnect())
            except Exception as e:
                logger.warning(f"Error disconnecting client for user {user_id} during cleanup: {e}")
            finally:
                del _auth_clients[user_id]
        # Always try to remove the session file
        try:
            os.remove(f"auth_{user_id}.session")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Error removing session file for user {user_id} during cleanup: {e}")

    @classmethod
    async def get_qr_login_url(cls, user_id: int, api_id: int, api_hash: str) -> str:
        """Генерирует QR-код для входа и сохраняет клиент."""
        cls.cleanup_auth(user_id)

        client = Client(
            name=f"auth_{user_id}",
            api_id=api_id,
            api_hash=api_hash,
            app_version="Telegram Android 10.0.0",
            device_model="Android 13",
            system_version="SDK 33",
            lang_code="en",
        )

        await client.connect()

        # Use raw API to export login token for QR code
        result = await client.invoke(
            functions.auth.ExportLoginToken(
                api_id=api_id,
                api_hash=api_hash,
                except_ids=[]
            )
        )

        if isinstance(result, types.auth.LoginToken):
            encoded_token = base64.urlsafe_b64encode(result.token).decode().rstrip("=")
            qr_code_url = f"tg://login?token={encoded_token}"
            _auth_clients[user_id] = client
            return qr_code_url
        else:
            await client.disconnect()
            raise Exception("Failed to export login token")

    @classmethod
    async def wait_for_qr_login(cls, user_id: int, api_id: int, api_hash: str, timeout: int = 60) -> Dict[str, Any]:
        """Ожидает входа по QR-коду и возвращает результат."""
        if user_id not in _auth_clients:
            return {"success": False, "error": "No auth client found"}

        client = _auth_clients[user_id]

        try:
            start_time = asyncio.get_event_loop().time()

            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    return {"success": False, "error": "timeout"}

                try:
                    result = await client.invoke(
                        functions.auth.ExportLoginToken(
                            api_id=api_id,
                            api_hash=api_hash,
                            except_ids=[]
                        )
                    )

                    if isinstance(result, types.auth.LoginTokenSuccess):
                        # Successfully logged in
                        session_string = await client.export_session_string()
                        return {"success": True, "session_string": session_string, "need_2fa": False}

                    elif isinstance(result, types.auth.LoginTokenMigrateTo):
                        # Need to migrate to another DC
                        await client.disconnect()

                        client = Client(
                            name=f"auth_{user_id}",
                            api_id=api_id,
                            api_hash=api_hash,
                            app_version="Telegram Android 10.0.0",
                            device_model="Android 13",
                            system_version="SDK 33",
                            lang_code="en",
                        )
                        await client.connect()
                        _auth_clients[user_id] = client

                        # Import the token on the new DC
                        import_result = await client.invoke(
                            functions.auth.ImportLoginToken(token=result.token)
                        )

                        if isinstance(import_result, types.auth.LoginTokenSuccess):
                            session_string = await client.export_session_string()
                            return {"success": True, "session_string": session_string, "need_2fa": False}
                        elif isinstance(import_result, types.auth.Authorization):
                            session_string = await client.export_session_string()
                            return {"success": True, "session_string": session_string, "need_2fa": False}

                    elif isinstance(result, types.auth.LoginToken):
                        # Token refreshed, still waiting - generate new QR URL
                        pass

                except Exception as e:
                    error_str = str(e).lower()
                    if "session_password_needed" in error_str or "password" in error_str:
                        return {"success": False, "need_2fa": True}
                    logger.debug(f"QR poll error (may be normal): {e}")

                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"QR login wait error for user {user_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if client.is_connected:
                await client.disconnect()
            cls.cleanup_auth(user_id)

    @classmethod
    async def refresh_qr_token(cls, user_id: int, api_id: int, api_hash: str) -> Optional[str]:
        """Обновляет QR токен и возвращает новый URL."""
        if user_id not in _auth_clients:
            return None

        client = _auth_clients[user_id]

        try:
            result = await client.invoke(
                functions.auth.ExportLoginToken(
                    api_id=api_id,
                    api_hash=api_hash,
                    except_ids=[]
                )
            )

            if isinstance(result, types.auth.LoginToken):
                encoded_token = base64.urlsafe_b64encode(result.token).decode().rstrip("=")
                return f"tg://login?token={encoded_token}"
        except Exception as e:
            logger.error(f"Error refreshing QR token: {e}")

        return None

    async def get_dialogs(self) -> List[Dict[str, Any]]:
        client = await self._get_client()

        try:
            await client.start()

            groups = []
            seen_ids = set()  # Для дедупликации по ID
            seen_names = {}   # Для дедупликации по названию (name -> id)

            async for dialog in client.get_dialogs():
                chat: Chat = dialog.chat

                if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    chat_id = chat.id
                    chat_name = chat.title or "Без названия"

                    # Пропускаем если уже видели этот ID
                    if chat_id in seen_ids:
                        continue

                    # Если группа с таким названием уже есть - используем supergroup ID
                    # (при миграции group -> supergroup, supergroup обычно имеет -100 префикс)
                    if chat_name in seen_names:
                        existing_id = seen_names[chat_name]
                        # Предпочитаем supergroup (ID с -100)
                        if str(chat_id).startswith("-100") and not str(existing_id).startswith("-100"):
                            # Заменяем старую группу на supergroup
                            groups = [g for g in groups if g["id"] != existing_id]
                            seen_ids.discard(existing_id)
                        else:
                            # Оставляем существующую
                            continue

                    seen_ids.add(chat_id)
                    seen_names[chat_name] = chat_id

                    groups.append({
                        "id": chat_id,
                        "name": chat_name,
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

            # Пробуем разные варианты ID
            chat_ids_to_try = [chat_id]

            chat_id_str = str(chat_id)
            # Если ID не начинается с -100, добавляем вариант с -100
            if chat_id_str.startswith("-") and not chat_id_str.startswith("-100"):
                chat_ids_to_try.append(int("-100" + chat_id_str[1:]))
            # Если ID начинается с -100, добавляем вариант без 100
            elif chat_id_str.startswith("-100"):
                chat_ids_to_try.append(int("-" + chat_id_str[4:]))

            last_error = None
            for try_chat_id in chat_ids_to_try:
                try:
                    # Сначала пробуем получить чат, чтобы Pyrogram знал о нём
                    try:
                        await client.get_chat(try_chat_id)
                    except Exception:
                        pass  # Игнорируем ошибку получения чата

                    await client.send_message(
                        chat_id=try_chat_id,
                        text=text,
                        reply_to_message_id=message_id,
                    )
                    logger.info(f"Successfully sent reply to chat {try_chat_id}")
                    await client.stop()
                    return True

                except Exception as e:
                    last_error = e
                    logger.warning(f"Failed to send to {try_chat_id}: {e}")
                    continue

            await client.stop()
            raise last_error or Exception("Failed to send message")

        except Exception as e:
            logger.error(f"Error sending reply to chat {chat_id}: {e}")
            try:
                await client.stop()
            except:
                pass
            raise

    async def forward_message(
        self,
        from_chat_id: int,
        message_id: int,
        to_chat_id: int,
    ) -> bool:
        """Пересылает сообщение пользователю"""
        client = await self._get_client()

        try:
            await client.start()

            # Пробуем разные варианты ID для from_chat_id
            chat_ids_to_try = [from_chat_id]

            chat_id_str = str(from_chat_id)
            if chat_id_str.startswith("-") and not chat_id_str.startswith("-100"):
                chat_ids_to_try.append(int("-100" + chat_id_str[1:]))
            elif chat_id_str.startswith("-100"):
                chat_ids_to_try.append(int("-" + chat_id_str[4:]))

            last_error = None
            for try_chat_id in chat_ids_to_try:
                try:
                    await client.forward_messages(
                        chat_id=to_chat_id,
                        from_chat_id=try_chat_id,
                        message_ids=message_id,
                    )
                    logger.info(f"Successfully forwarded message from {try_chat_id} to {to_chat_id}")
                    await client.stop()
                    return True

                except Exception as e:
                    last_error = e
                    logger.warning(f"Failed to forward from {try_chat_id}: {e}")
                    continue

            await client.stop()
            raise last_error or Exception("Failed to forward message")

        except Exception as e:
            logger.error(f"Error forwarding message: {e}")
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