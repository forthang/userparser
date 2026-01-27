from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    User, Group, Keyword, City, Payment, Order,
    BlacklistedGroup, BotSettings, UserLog, GroupMessage,
    MonitorWorker, GroupAssignment, SharedGroupMessage, OrderDelivery,
    DEFAULT_KEYWORDS, DEFAULT_HELP_TEXT
)


class UserCRUD:
    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
    ) -> User:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        for word in DEFAULT_KEYWORDS:
            keyword = Keyword(user_id=user.id, word=word, is_default=True)
            session.add(keyword)
        await session.commit()

        return user

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
    ) -> User:
        user = await UserCRUD.get_by_telegram_id(session, telegram_id)
        if user is None:
            try:
                user = await UserCRUD.create(session, telegram_id, username)
            except Exception:
                # Race condition - user was created by another request
                await session.rollback()
                user = await UserCRUD.get_by_telegram_id(session, telegram_id)
        return user

    @staticmethod
    async def update_session(
        session: AsyncSession,
        user_id: int,
        session_string: str,
        phone: Optional[str] = None,
    ) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(session_string=session_string, phone=phone)
        )
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def clear_session(session: AsyncSession, user_id: int) -> None:
        """Удаляет сессию юзербота (разлогин)"""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(session_string=None, monitoring_enabled=False)
        )
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def update_subscription(
        session: AsyncSession,
        user_id: int,
        days: int,
    ) -> None:
        user = await session.get(User, user_id)
        if user:
            if user.subscription_end and user.subscription_end > datetime.utcnow():
                new_end = user.subscription_end + timedelta(days=days)
            else:
                new_end = datetime.utcnow() + timedelta(days=days)
            user.subscription_end = new_end
            await session.commit()

    @staticmethod
    async def toggle_monitoring(
        session: AsyncSession,
        user_id: int,
        enabled: bool,
    ) -> None:
        stmt = update(User).where(User.id == user_id).values(monitoring_enabled=enabled)
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def update_response_text(
        session: AsyncSession,
        user_id: int,
        response_text: str,
    ) -> None:
        stmt = update(User).where(User.id == user_id).values(response_text=response_text)
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def get_active_users_with_monitoring(session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.monitoring_enabled == True,
                User.session_string.isnot(None),
                User.subscription_end > datetime.utcnow(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_expiring_subscriptions(
        session: AsyncSession,
        days_before: int = 3,
    ) -> List[User]:
        threshold = datetime.utcnow() + timedelta(days=days_before)
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.subscription_end.isnot(None),
                User.subscription_end <= threshold,
                User.subscription_end > datetime.utcnow(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def deactivate_expired(session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.subscription_end.isnot(None),
                User.subscription_end <= datetime.utcnow(),
            )
        )
        expired_users = list(result.scalars().all())

        for user in expired_users:
            user.is_active = False
            user.monitoring_enabled = False
            user.session_string = None

        await session.commit()
        return expired_users

    @staticmethod
    async def delete_user_data(session: AsyncSession, user_id: int) -> None:
        await session.execute(delete(Order).where(Order.user_id == user_id))
        await session.execute(delete(Group).where(Group.user_id == user_id))
        await session.execute(delete(Keyword).where(Keyword.user_id == user_id))
        await session.execute(delete(City).where(City.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()

    @staticmethod
    async def set_banned(session: AsyncSession, user_id: int, is_banned: bool) -> None:
        stmt = update(User).where(User.id == user_id).values(is_banned=is_banned)
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def set_admin(session: AsyncSession, user_id: int, is_admin: bool) -> None:
        stmt = update(User).where(User.id == user_id).values(is_admin=is_admin)
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def get_all_users(session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User).where(User.is_active == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_all_admins(session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User).where(User.is_admin == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def search_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_users_count(session: AsyncSession) -> dict:
        """Возвращает статистику по пользователям"""
        all_users = await session.execute(select(User))
        users = list(all_users.scalars().all())

        return {
            "total": len(users),
            "active": len([u for u in users if u.is_active]),
            "with_subscription": len([u for u in users if u.is_subscription_active]),
            "banned": len([u for u in users if u.is_banned]),
            "admins": len([u for u in users if u.is_admin]),
        }


class GroupCRUD:
    @staticmethod
    async def get_user_groups(session: AsyncSession, user_id: int) -> List[Group]:
        result = await session.execute(
            select(Group).where(Group.user_id == user_id).order_by(Group.is_enabled.desc(), Group.group_name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_enabled_groups(session: AsyncSession, user_id: int) -> List[Group]:
        result = await session.execute(
            select(Group).where(Group.user_id == user_id, Group.is_enabled == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_or_update(
        session: AsyncSession,
        user_id: int,
        telegram_group_id: int,
        group_name: str,
    ) -> Group:
        result = await session.execute(
            select(Group).where(
                Group.user_id == user_id,
                Group.telegram_group_id == telegram_group_id,
            )
        )
        group = result.scalar_one_or_none()

        if group is None:
            group = Group(
                user_id=user_id,
                telegram_group_id=telegram_group_id,
                group_name=group_name,
                is_enabled=False,
            )
            session.add(group)
        else:
            group.group_name = group_name

        await session.commit()
        await session.refresh(group)
        return group

    @staticmethod
    async def toggle_group(
        session: AsyncSession,
        group_id: int,
    ) -> bool:
        group = await session.get(Group, group_id)
        if group:
            group.is_enabled = not group.is_enabled
            await session.commit()
            return group.is_enabled
        return False

    @staticmethod
    async def sync_groups(
        session: AsyncSession,
        user_id: int,
        telegram_groups: List[dict],
    ) -> None:
        # Сначала удалим дубликаты по названию (оставляем supergroup версии)
        existing_groups = await GroupCRUD.get_user_groups(session, user_id)
        seen_names = {}
        for group in existing_groups:
            if group.group_name in seen_names:
                # Есть дубликат - удаляем один из них
                existing_id = seen_names[group.group_name]
                # Предпочитаем supergroup (ID с -100)
                if str(group.telegram_group_id).startswith("-100") and not str(existing_id).startswith("-100"):
                    # Удаляем старую группу (без -100)
                    await session.execute(
                        delete(Group).where(
                            Group.user_id == user_id,
                            Group.telegram_group_id == existing_id
                        )
                    )
                    seen_names[group.group_name] = group.telegram_group_id
                else:
                    # Удаляем текущую группу
                    await session.execute(
                        delete(Group).where(Group.id == group.id)
                    )
            else:
                seen_names[group.group_name] = group.telegram_group_id

        await session.commit()

        # Теперь добавляем/обновляем группы
        for tg_group in telegram_groups:
            await GroupCRUD.add_or_update(
                session,
                user_id,
                tg_group["id"],
                tg_group["name"],
            )


class KeywordCRUD:
    @staticmethod
    async def get_user_keywords(session: AsyncSession, user_id: int) -> List[Keyword]:
        result = await session.execute(
            select(Keyword).where(Keyword.user_id == user_id).order_by(Keyword.is_default.desc(), Keyword.word)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_keyword(
        session: AsyncSession,
        user_id: int,
        word: str,
    ) -> Keyword:
        keyword = Keyword(user_id=user_id, word=word.lower(), is_default=False)
        session.add(keyword)
        await session.commit()
        await session.refresh(keyword)
        return keyword

    @staticmethod
    async def delete_keyword(session: AsyncSession, keyword_id: int) -> None:
        await session.execute(delete(Keyword).where(Keyword.id == keyword_id))
        await session.commit()

    @staticmethod
    async def delete_all_keywords(session: AsyncSession, user_id: int) -> None:
        await session.execute(delete(Keyword).where(Keyword.user_id == user_id))
        await session.commit()

    @staticmethod
    async def restore_defaults(session: AsyncSession, user_id: int) -> None:
        await KeywordCRUD.delete_all_keywords(session, user_id)
        for word in DEFAULT_KEYWORDS:
            keyword = Keyword(user_id=user_id, word=word, is_default=True)
            session.add(keyword)
        await session.commit()


class CityCRUD:
    @staticmethod
    async def get_user_cities(session: AsyncSession, user_id: int) -> List[City]:
        result = await session.execute(
            select(City).where(City.user_id == user_id).order_by(City.city_name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_city(
        session: AsyncSession,
        user_id: int,
        city_name: str,
        variations: List[str],
    ) -> City:
        city = City(
            user_id=user_id,
            city_name=city_name,
            variations=variations,
        )
        session.add(city)
        await session.commit()
        await session.refresh(city)
        return city

    @staticmethod
    async def delete_city(session: AsyncSession, city_id: int) -> None:
        await session.execute(delete(City).where(City.id == city_id))
        await session.commit()

    @staticmethod
    async def delete_all_cities(session: AsyncSession, user_id: int) -> None:
        await session.execute(delete(City).where(City.user_id == user_id))
        await session.commit()


class PaymentCRUD:
    @staticmethod
    async def create_payment(
        session: AsyncSession,
        user_id: int,
        amount: float,
        payment_id: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            amount=amount,
            payment_id=payment_id,
            status="pending",
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    @staticmethod
    async def confirm_payment(
        session: AsyncSession,
        payment_id: str,
    ) -> Optional[Payment]:
        result = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = "confirmed"
            payment.confirmed_at = datetime.utcnow()
            await session.commit()
            await session.refresh(payment)
        return payment

    @staticmethod
    async def get_by_payment_id(
        session: AsyncSession,
        payment_id: str,
    ) -> Optional[Payment]:
        result = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        return result.scalar_one_or_none()


class OrderCRUD:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        group_id: int,
        telegram_group_id: int,
        message_id: int,
        message_text: str,
    ) -> Order:
        order = Order(
            user_id=user_id,
            group_id=group_id,
            telegram_group_id=telegram_group_id,
            message_id=message_id,
            message_text=message_text,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    @staticmethod
    async def mark_responded(session: AsyncSession, order_id: int) -> None:
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(responded=True, responded_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def get_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
        return await session.get(Order, order_id)


class BlacklistedGroupCRUD:
    @staticmethod
    async def get_all(session: AsyncSession) -> List[BlacklistedGroup]:
        result = await session.execute(
            select(BlacklistedGroup).order_by(BlacklistedGroup.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def add(
        session: AsyncSession,
        telegram_group_id: int,
        group_name: str,
        added_by: int,
        reason: str = None,
    ) -> BlacklistedGroup:
        blacklisted = BlacklistedGroup(
            telegram_group_id=telegram_group_id,
            group_name=group_name,
            added_by=added_by,
            reason=reason,
        )
        session.add(blacklisted)
        await session.commit()
        await session.refresh(blacklisted)
        return blacklisted

    @staticmethod
    async def remove(session: AsyncSession, telegram_group_id: int) -> bool:
        result = await session.execute(
            delete(BlacklistedGroup).where(BlacklistedGroup.telegram_group_id == telegram_group_id)
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def is_blacklisted(session: AsyncSession, telegram_group_id: int) -> bool:
        result = await session.execute(
            select(BlacklistedGroup).where(BlacklistedGroup.telegram_group_id == telegram_group_id)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_blacklisted_ids(session: AsyncSession) -> set:
        """Возвращает set ID всех заблокированных групп"""
        result = await session.execute(select(BlacklistedGroup.telegram_group_id))
        return {row[0] for row in result.fetchall()}


class BotSettingsCRUD:
    @staticmethod
    async def get(session: AsyncSession, key: str, default: str = "") -> str:
        """Получает значение настройки по ключу"""
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            return setting.value
        return default

    @staticmethod
    async def set(session: AsyncSession, key: str, value: str) -> None:
        """Устанавливает значение настройки"""
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
        else:
            setting = BotSettings(key=key, value=value)
            session.add(setting)

        await session.commit()

    @staticmethod
    async def get_help_text(session: AsyncSession) -> str:
        """Получает текст помощи"""
        return await BotSettingsCRUD.get(session, "help_text", DEFAULT_HELP_TEXT)

    @staticmethod
    async def set_help_text(session: AsyncSession, text: str) -> None:
        """Устанавливает текст помощи"""
        await BotSettingsCRUD.set(session, "help_text", text)


class UserLogCRUD:
    """CRUD операции для логов действий пользователей"""

    @staticmethod
    async def add(
        session: AsyncSession,
        user_id: int,
        action: str,
        details: Optional[str] = None,
    ) -> UserLog:
        """Добавляет запись лога"""
        log = UserLog(
            user_id=user_id,
            action=action,
            details=details,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    @staticmethod
    async def get_user_logs(
        session: AsyncSession,
        user_id: int,
        limit: int = 100,
    ) -> List[UserLog]:
        """Получает логи пользователя"""
        result = await session.execute(
            select(UserLog)
            .where(UserLog.user_id == user_id)
            .order_by(UserLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_recent_errors(
        session: AsyncSession,
        limit: int = 50,
    ) -> List[UserLog]:
        """Получает последние ошибки"""
        result = await session.execute(
            select(UserLog)
            .where(UserLog.action.like("%error%"))
            .order_by(UserLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class GroupMessageCRUD:
    """CRUD операции для сообщений из групп"""

    @staticmethod
    async def add(
        session: AsyncSession,
        user_id: int,
        group_id: int,
        telegram_group_id: int,
        message_id: int,
        message_text: str,
        matched_keyword: Optional[str] = None,
        matched_city: Optional[str] = None,
    ) -> GroupMessage:
        """Добавляет сообщение"""
        msg = GroupMessage(
            user_id=user_id,
            group_id=group_id,
            telegram_group_id=telegram_group_id,
            message_id=message_id,
            message_text=message_text,
            matched_keyword=matched_keyword,
            matched_city=matched_city,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg

    @staticmethod
    async def get_user_messages(
        session: AsyncSession,
        user_id: int,
        limit: int = 500,
    ) -> List[GroupMessage]:
        """Получает сообщения пользователя за последние 24 часа"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            select(GroupMessage)
            .where(
                GroupMessage.user_id == user_id,
                GroupMessage.created_at >= threshold
            )
            .order_by(GroupMessage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_messages_filtered(
        session: AsyncSession,
        user_id: int,
        matched_only: bool = False,
        unmatched_only: bool = False,
        limit: int = 500,
    ) -> List[GroupMessage]:
        """Получает отфильтрованные сообщения"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        query = select(GroupMessage).where(
            GroupMessage.user_id == user_id,
            GroupMessage.created_at >= threshold
        )

        if matched_only:
            query = query.where(GroupMessage.matched_keyword.isnot(None))
        elif unmatched_only:
            query = query.where(GroupMessage.matched_keyword.is_(None))

        result = await session.execute(
            query.order_by(GroupMessage.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def cleanup_old_messages(session: AsyncSession) -> int:
        """Удаляет сообщения старше 24 часов"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            delete(GroupMessage).where(GroupMessage.created_at < threshold)
        )
        await session.commit()
        return result.rowcount


# ============ Shared Monitoring Pool CRUD ============

class MonitorWorkerCRUD:
    """CRUD операции для воркер-аккаунтов"""

    @staticmethod
    async def get_all(session: AsyncSession) -> List[MonitorWorker]:
        """Получает всех воркеров"""
        result = await session.execute(
            select(MonitorWorker).order_by(MonitorWorker.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active(session: AsyncSession) -> List[MonitorWorker]:
        """Получает активных воркеров"""
        result = await session.execute(
            select(MonitorWorker)
            .where(MonitorWorker.is_active == True)
            .order_by(MonitorWorker.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, worker_id: int) -> Optional[MonitorWorker]:
        """Получает воркера по ID"""
        return await session.get(MonitorWorker, worker_id)

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        session_string: str,
        phone: Optional[str] = None,
        max_groups: int = 50,
    ) -> MonitorWorker:
        """Создает нового воркера"""
        worker = MonitorWorker(
            name=name,
            session_string=session_string,
            phone=phone,
            max_groups=max_groups,
        )
        session.add(worker)
        await session.commit()
        await session.refresh(worker)
        return worker

    @staticmethod
    async def update_status(
        session: AsyncSession,
        worker_id: int,
        is_active: bool,
        last_error: Optional[str] = None,
    ) -> None:
        """Обновляет статус воркера"""
        stmt = (
            update(MonitorWorker)
            .where(MonitorWorker.id == worker_id)
            .values(is_active=is_active, last_error=last_error, last_active_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def delete(session: AsyncSession, worker_id: int) -> bool:
        """Удаляет воркера"""
        result = await session.execute(
            delete(MonitorWorker).where(MonitorWorker.id == worker_id)
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_worker_with_least_groups(session: AsyncSession) -> Optional[MonitorWorker]:
        """Получает воркера с наименьшим количеством групп"""
        workers = await MonitorWorkerCRUD.get_active(session)
        if not workers:
            return None

        # Подсчитываем количество групп для каждого воркера
        min_count = float('inf')
        best_worker = None

        for worker in workers:
            result = await session.execute(
                select(GroupAssignment)
                .where(
                    GroupAssignment.worker_id == worker.id,
                    GroupAssignment.is_active == True
                )
            )
            count = len(list(result.scalars().all()))
            if count < min_count and count < worker.max_groups:
                min_count = count
                best_worker = worker

        return best_worker


class GroupAssignmentCRUD:
    """CRUD операции для назначения групп на воркеров"""

    @staticmethod
    async def get_all(session: AsyncSession) -> List[GroupAssignment]:
        """Получает все назначения"""
        result = await session.execute(
            select(GroupAssignment).order_by(GroupAssignment.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_group_id(
        session: AsyncSession,
        telegram_group_id: int,
    ) -> Optional[GroupAssignment]:
        """Получает назначение по telegram_group_id"""
        result = await session.execute(
            select(GroupAssignment)
            .where(
                GroupAssignment.telegram_group_id == telegram_group_id,
                GroupAssignment.is_active == True
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_worker_groups(
        session: AsyncSession,
        worker_id: int,
    ) -> List[GroupAssignment]:
        """Получает группы воркера"""
        result = await session.execute(
            select(GroupAssignment)
            .where(
                GroupAssignment.worker_id == worker_id,
                GroupAssignment.is_active == True
            )
            .order_by(GroupAssignment.group_name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def assign_group(
        session: AsyncSession,
        worker_id: int,
        telegram_group_id: int,
        group_name: str,
    ) -> GroupAssignment:
        """Назначает группу на воркера"""
        # Проверяем, не назначена ли уже
        existing = await GroupAssignmentCRUD.get_by_group_id(session, telegram_group_id)
        if existing:
            return existing

        assignment = GroupAssignment(
            worker_id=worker_id,
            telegram_group_id=telegram_group_id,
            group_name=group_name,
        )
        session.add(assignment)
        await session.commit()
        await session.refresh(assignment)
        return assignment

    @staticmethod
    async def unassign_group(
        session: AsyncSession,
        telegram_group_id: int,
    ) -> bool:
        """Убирает назначение группы"""
        result = await session.execute(
            delete(GroupAssignment)
            .where(GroupAssignment.telegram_group_id == telegram_group_id)
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_all_monitored_groups(session: AsyncSession) -> List[int]:
        """Получает ID всех мониторимых групп"""
        result = await session.execute(
            select(GroupAssignment.telegram_group_id)
            .where(GroupAssignment.is_active == True)
        )
        return [row[0] for row in result.fetchall()]


class SharedGroupMessageCRUD:
    """CRUD операции для сообщений общего пула"""

    @staticmethod
    async def add(
        session: AsyncSession,
        worker_id: int,
        telegram_group_id: int,
        group_name: str,
        message_id: int,
        message_text: str,
        sender_id: Optional[int] = None,
        sender_username: Optional[str] = None,
    ) -> SharedGroupMessage:
        """Добавляет сообщение"""
        msg = SharedGroupMessage(
            worker_id=worker_id,
            telegram_group_id=telegram_group_id,
            group_name=group_name,
            message_id=message_id,
            message_text=message_text,
            sender_id=sender_id,
            sender_username=sender_username,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg

    @staticmethod
    async def get_by_group(
        session: AsyncSession,
        telegram_group_id: int,
        limit: int = 500,
    ) -> List[SharedGroupMessage]:
        """Получает сообщения группы за последние 24 часа"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            select(SharedGroupMessage)
            .where(
                SharedGroupMessage.telegram_group_id == telegram_group_id,
                SharedGroupMessage.created_at >= threshold
            )
            .order_by(SharedGroupMessage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_all_recent(
        session: AsyncSession,
        limit: int = 1000,
    ) -> List[SharedGroupMessage]:
        """Получает все недавние сообщения"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            select(SharedGroupMessage)
            .where(SharedGroupMessage.created_at >= threshold)
            .order_by(SharedGroupMessage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def cleanup_old(session: AsyncSession) -> int:
        """Удаляет сообщения старше 24 часов"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            delete(SharedGroupMessage).where(SharedGroupMessage.created_at < threshold)
        )
        await session.commit()
        return result.rowcount


class OrderDeliveryCRUD:
    """CRUD операции для доставки заказов"""

    @staticmethod
    async def add(
        session: AsyncSession,
        shared_message_id: int,
        user_id: int,
        matched_keyword: str,
        matched_city: Optional[str] = None,
    ) -> OrderDelivery:
        """Добавляет запись о доставке"""
        delivery = OrderDelivery(
            shared_message_id=shared_message_id,
            user_id=user_id,
            matched_keyword=matched_keyword,
            matched_city=matched_city,
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)
        return delivery

    @staticmethod
    async def get_by_message(
        session: AsyncSession,
        shared_message_id: int,
    ) -> List[OrderDelivery]:
        """Получает все доставки для сообщения"""
        result = await session.execute(
            select(OrderDelivery)
            .where(OrderDelivery.shared_message_id == shared_message_id)
            .order_by(OrderDelivery.delivered_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_user(
        session: AsyncSession,
        user_id: int,
        limit: int = 100,
    ) -> List[OrderDelivery]:
        """Получает доставки пользователя"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            select(OrderDelivery)
            .where(
                OrderDelivery.user_id == user_id,
                OrderDelivery.delivered_at >= threshold
            )
            .order_by(OrderDelivery.delivered_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_stats_by_group(
        session: AsyncSession,
        telegram_group_id: int,
    ) -> dict:
        """Получает статистику доставок по группе"""
        threshold = datetime.utcnow() - timedelta(hours=24)

        # Получаем сообщения группы
        messages = await session.execute(
            select(SharedGroupMessage)
            .where(
                SharedGroupMessage.telegram_group_id == telegram_group_id,
                SharedGroupMessage.created_at >= threshold
            )
        )
        message_ids = [m.id for m in messages.scalars().all()]

        if not message_ids:
            return {"total_messages": 0, "delivered_orders": 0, "users_received": 0}

        # Получаем доставки
        deliveries = await session.execute(
            select(OrderDelivery)
            .where(OrderDelivery.shared_message_id.in_(message_ids))
        )
        delivery_list = list(deliveries.scalars().all())

        return {
            "total_messages": len(message_ids),
            "delivered_orders": len(delivery_list),
            "users_received": len(set(d.user_id for d in delivery_list)),
        }

    @staticmethod
    async def cleanup_old(session: AsyncSession) -> int:
        """Удаляет старые доставки (старше 24 часов)"""
        threshold = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            delete(OrderDelivery).where(OrderDelivery.delivered_at < threshold)
        )
        await session.commit()
        return result.rowcount
