import asyncio
import logging
from typing import Dict, Set, List, Optional, Callable, Awaitable
from datetime import datetime
from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from pyrogram.enums import ChatType

from bot.config import config
from bot.database.connection import async_session
from bot.database.crud import (
    MonitorWorkerCRUD,
    GroupAssignmentCRUD,
    SharedGroupMessageCRUD,
    OrderDeliveryCRUD,
    UserCRUD,
    GroupCRUD,
    KeywordCRUD,
    CityCRUD,
)
from bot.database.models import MonitorWorker, User
from bot.services.parser import MessageParser

logger = logging.getLogger(__name__)


class SharedWorkerClient:
    """Клиент воркера для общего пула мониторинга"""

    def __init__(
        self,
        worker: MonitorWorker,
        on_message_callback: Callable[[int, int, str, int, str, Message, int], Awaitable[None]],
    ):
        self.worker_id = worker.id
        self.worker_name = worker.name
        self.session_string = worker.session_string

        self.client = Client(
            name=f"shared_worker_{worker.id}",
            api_id=config.telegram_api.api_id,
            api_hash=config.telegram_api.api_hash,
            session_string=worker.session_string,
            in_memory=True,
        )

        self.on_message_callback = on_message_callback
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
        logger.info(f"SharedWorker {self.worker_name} started with {len(self.monitored_groups)} groups")

    async def stop(self):
        if not self._running:
            return

        self._running = False
        await self.client.stop()
        logger.info(f"SharedWorker {self.worker_name} stopped")

    async def _load_monitored_groups(self):
        """Загружает список групп для мониторинга"""
        async with async_session() as session:
            assignments = await GroupAssignmentCRUD.get_worker_groups(session, self.worker_id)
            self.monitored_groups = {a.telegram_group_id for a in assignments}

        logger.info(f"Worker {self.worker_name} loaded {len(self.monitored_groups)} groups")

    async def refresh_groups(self):
        """Обновляет список групп"""
        await self._load_monitored_groups()

    async def _handle_message(self, client: Client, message: Message):
        try:
            if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                return

            if message.chat.id not in self.monitored_groups:
                return

            if not message.text:
                return

            await self.on_message_callback(
                self.worker_id,
                message.chat.id,
                message.chat.title or "Unknown",
                message.id,
                message.text,
                message,
                message.from_user.id if message.from_user else 0,
            )

        except Exception as e:
            logger.error(f"Error handling message in worker {self.worker_name}: {e}")


class SharedMonitorPool:
    """Общий пул мониторинга - один воркер на несколько пользователей"""

    _instance = None
    _workers: Dict[int, SharedWorkerClient] = {}
    _lock = asyncio.Lock()
    _bot = None  # Bot instance для отправки уведомлений

    @classmethod
    def get_instance(cls) -> "SharedMonitorPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_bot(self, bot):
        """Устанавливает Bot instance для отправки уведомлений"""
        self._bot = bot

    async def start_all_workers(self):
        """Запускает всех активных воркеров"""
        async with async_session() as session:
            workers = await MonitorWorkerCRUD.get_active(session)

        for worker in workers:
            await self._start_worker(worker)

        logger.info(f"Started {len(self._workers)} shared workers")

    async def _start_worker(self, worker: MonitorWorker) -> bool:
        """Запускает одного воркера"""
        async with self._lock:
            if worker.id in self._workers:
                return True

            try:
                client = SharedWorkerClient(
                    worker=worker,
                    on_message_callback=self._on_message,
                )
                await client.start()
                self._workers[worker.id] = client

                # Обновляем статус в БД
                async with async_session() as session:
                    await MonitorWorkerCRUD.update_status(
                        session, worker.id, is_active=True, last_error=None
                    )

                return True

            except Exception as e:
                logger.error(f"Error starting worker {worker.name}: {e}")

                # Записываем ошибку в БД
                async with async_session() as session:
                    await MonitorWorkerCRUD.update_status(
                        session, worker.id, is_active=False, last_error=str(e)
                    )

                return False

    async def stop_worker(self, worker_id: int):
        """Останавливает воркера"""
        async with self._lock:
            if worker_id in self._workers:
                await self._workers[worker_id].stop()
                del self._workers[worker_id]

    async def stop_all(self):
        """Останавливает всех воркеров"""
        async with self._lock:
            for worker_id in list(self._workers.keys()):
                await self._workers[worker_id].stop()
            self._workers.clear()

        logger.info("All shared workers stopped")

    async def refresh_worker_groups(self, worker_id: int):
        """Обновляет группы воркера"""
        if worker_id in self._workers:
            await self._workers[worker_id].refresh_groups()

    async def refresh_all_groups(self):
        """Обновляет группы всех воркеров"""
        for worker in self._workers.values():
            await worker.refresh_groups()

    def get_active_workers_count(self) -> int:
        return len(self._workers)

    async def _on_message(
        self,
        worker_id: int,
        telegram_group_id: int,
        group_name: str,
        message_id: int,
        message_text: str,
        message: Message,
        sender_id: int,
    ):
        """Обработка входящего сообщения"""
        try:
            # Сохраняем сообщение в общую историю
            async with async_session() as session:
                shared_msg = await SharedGroupMessageCRUD.add(
                    session,
                    worker_id=worker_id,
                    telegram_group_id=telegram_group_id,
                    group_name=group_name,
                    message_id=message_id,
                    message_text=message_text,
                    sender_id=sender_id,
                    sender_username=message.from_user.username if message.from_user else None,
                )

            # Находим всех пользователей, которые мониторят эту группу
            await self._dispatch_to_users(
                shared_msg.id,
                telegram_group_id,
                group_name,
                message_id,
                message_text,
                message,
            )

        except Exception as e:
            logger.error(f"Error processing shared message: {e}")

    async def _dispatch_to_users(
        self,
        shared_message_id: int,
        telegram_group_id: int,
        group_name: str,
        message_id: int,
        message_text: str,
        message: Message,
    ):
        """Рассылает уведомления пользователям, которые мониторят эту группу"""
        async with async_session() as session:
            # Находим пользователей с этой группой и активной подпиской
            from sqlalchemy import select
            from bot.database.models import Group, User

            result = await session.execute(
                select(Group, User)
                .join(User, Group.user_id == User.id)
                .where(
                    Group.telegram_group_id == telegram_group_id,
                    Group.is_enabled == True,
                    User.monitoring_enabled == True,
                    User.subscription_end > datetime.utcnow(),
                    User.is_banned == False,
                )
            )

            user_groups = result.fetchall()

            for group, user in user_groups:
                try:
                    # Получаем ключевые слова и города пользователя
                    keywords = await KeywordCRUD.get_user_keywords(session, user.id)
                    cities = await CityCRUD.get_user_cities(session, user.id)

                    if not keywords:
                        continue

                    # Создаем парсер и проверяем сообщение
                    parser = MessageParser(keywords=keywords, cities=cities)
                    is_match, matched_keyword, matched_city = parser.check_message(message_text)

                    if is_match:
                        # Записываем доставку
                        await OrderDeliveryCRUD.add(
                            session,
                            shared_message_id=shared_message_id,
                            user_id=user.id,
                            matched_keyword=matched_keyword,
                            matched_city=matched_city,
                        )

                        # Отправляем уведомление
                        if self._bot:
                            notification = parser.format_notification(
                                message_text=message_text,
                                group_name=group_name,
                                keyword=matched_keyword,
                                city=matched_city,
                            )

                            await self._send_notification(
                                user=user,
                                group=group,
                                notification=notification,
                                message_id=message_id,
                                telegram_group_id=telegram_group_id,
                            )

                except Exception as e:
                    logger.error(f"Error dispatching to user {user.telegram_id}: {e}")

    async def _send_notification(
        self,
        user: User,
        group,
        notification: str,
        message_id: int,
        telegram_group_id: int,
    ):
        """Отправляет уведомление пользователю"""
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        try:
            builder = InlineKeyboardBuilder()

            # Кнопка "Откликнуться"
            if user.response_text:
                from bot.database.crud import OrderCRUD
                async with async_session() as session:
                    order = await OrderCRUD.create_order(
                        session,
                        user_id=user.id,
                        group_id=group.id,
                        telegram_group_id=telegram_group_id,
                        message_id=message_id,
                        message_text=notification[:500],
                    )
                    builder.row(
                        InlineKeyboardButton(
                            text="✅ Откликнуться",
                            callback_data=f"respond:{order.id}"
                        )
                    )

            # Ссылка на сообщение
            group_username = str(telegram_group_id).replace("-100", "")
            builder.row(
                InlineKeyboardButton(
                    text="📨 Открыть сообщение",
                    url=f"https://t.me/c/{group_username}/{message_id}"
                )
            )

            await self._bot.send_message(
                chat_id=user.telegram_id,
                text=notification,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )

            logger.info(f"Sent order notification to user {user.telegram_id}")

        except Exception as e:
            logger.error(f"Error sending notification to user {user.telegram_id}: {e}")


# ============ Group Distribution ============

class GroupDistributor:
    """Распределение групп по воркерам (равномерное)"""

    @staticmethod
    async def redistribute_groups():
        """
        Перераспределяет все группы равномерно по воркерам.
        Вызывается при добавлении/удалении воркеров или групп.
        """
        async with async_session() as session:
            # Получаем активных воркеров
            workers = await MonitorWorkerCRUD.get_active(session)
            if not workers:
                logger.warning("No active workers for redistribution")
                return

            # Получаем все уникальные группы, которые нужно мониторить
            from sqlalchemy import select, distinct
            from bot.database.models import Group, User

            result = await session.execute(
                select(distinct(Group.telegram_group_id), Group.group_name)
                .join(User, Group.user_id == User.id)
                .where(
                    Group.is_enabled == True,
                    User.monitoring_enabled == True,
                    User.subscription_end > datetime.utcnow(),
                )
            )

            groups_to_monitor = [(row[0], row[1]) for row in result.fetchall()]

            if not groups_to_monitor:
                logger.info("No groups to monitor")
                return

            # Равномерно распределяем группы
            worker_ids = [w.id for w in workers]
            num_workers = len(worker_ids)

            # Удаляем старые назначения
            from sqlalchemy import delete
            from bot.database.models import GroupAssignment
            await session.execute(delete(GroupAssignment))
            await session.commit()

            # Назначаем группы по кругу
            for i, (group_id, group_name) in enumerate(groups_to_monitor):
                worker_id = worker_ids[i % num_workers]
                await GroupAssignmentCRUD.assign_group(
                    session,
                    worker_id=worker_id,
                    telegram_group_id=group_id,
                    group_name=group_name,
                )

            logger.info(
                f"Redistributed {len(groups_to_monitor)} groups across {num_workers} workers"
            )

            # Обновляем группы в запущенных воркерах
            pool = SharedMonitorPool.get_instance()
            await pool.refresh_all_groups()

    @staticmethod
    async def assign_new_group(telegram_group_id: int, group_name: str) -> Optional[int]:
        """
        Назначает новую группу на воркера с наименьшей нагрузкой.
        Возвращает ID воркера.
        """
        async with async_session() as session:
            # Проверяем, не назначена ли уже
            existing = await GroupAssignmentCRUD.get_by_group_id(session, telegram_group_id)
            if existing:
                return existing.worker_id

            # Находим воркера с минимальным количеством групп
            worker = await MonitorWorkerCRUD.get_worker_with_least_groups(session)
            if not worker:
                logger.error("No available workers for new group")
                return None

            await GroupAssignmentCRUD.assign_group(
                session,
                worker_id=worker.id,
                telegram_group_id=telegram_group_id,
                group_name=group_name,
            )

            # Обновляем группы воркера
            pool = SharedMonitorPool.get_instance()
            await pool.refresh_worker_groups(worker.id)

            return worker.id

    @staticmethod
    async def get_distribution_stats() -> dict:
        """Возвращает статистику распределения"""
        async with async_session() as session:
            workers = await MonitorWorkerCRUD.get_all(session)
            stats = []

            for worker in workers:
                assignments = await GroupAssignmentCRUD.get_worker_groups(session, worker.id)
                stats.append({
                    "worker_id": worker.id,
                    "worker_name": worker.name,
                    "is_active": worker.is_active,
                    "groups_count": len(assignments),
                    "max_groups": worker.max_groups,
                    "last_error": worker.last_error,
                })

            return {
                "workers": stats,
                "total_workers": len(workers),
                "active_workers": len([w for w in workers if w.is_active]),
                "total_groups": sum(s["groups_count"] for s in stats),
            }


# Singleton instance
shared_pool = SharedMonitorPool.get_instance()
