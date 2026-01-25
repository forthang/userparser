from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    session_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="Я"
    )
    subscription_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    groups: Mapped[List["Group"]] = relationship(
        "Group", back_populates="user", cascade="all, delete-orphan"
    )
    keywords: Mapped[List["Keyword"]] = relationship(
        "Keyword", back_populates="user", cascade="all, delete-orphan"
    )
    cities: Mapped[List["City"]] = relationship(
        "City", back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="user", cascade="all, delete-orphan"
    )
    logs: Mapped[List["UserLog"]] = relationship(
        "UserLog", back_populates="user", cascade="all, delete-orphan"
    )
    group_messages: Mapped[List["GroupMessage"]] = relationship(
        "GroupMessage", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_subscription_active(self) -> bool:
        if self.subscription_end is None:
            return False
        return self.subscription_end > datetime.utcnow()

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    telegram_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="groups")

    def __repr__(self) -> str:
        return f"<Group(id={self.id}, name={self.group_name}, enabled={self.is_enabled})>"


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="keywords")

    def __repr__(self) -> str:
        return f"<Keyword(id={self.id}, word={self.word})>"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    city_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variations: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="cities")

    def __repr__(self) -> str:
        return f"<City(id={self.id}, name={self.city_name})>"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_id: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, amount={self.amount}, status={self.status})>"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    telegram_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    responded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="orders")
    group: Mapped["Group"] = relationship("Group")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, responded={self.responded})>"


class BlacklistedGroup(Base):
    """Глобальный черный список групп - группы которые нельзя мониторить"""
    __tablename__ = "blacklisted_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_group_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    group_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_by: Mapped[int] = mapped_column(BigInteger, nullable=False)  # admin telegram_id
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<BlacklistedGroup(id={self.id}, name={self.group_name})>"


class UserLog(Base):
    """Логи действий пользователей для админ-панели"""
    __tablename__ = "user_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # auth_start, auth_success, monitoring_on, error, etc.
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON с деталями
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="logs")

    def __repr__(self) -> str:
        return f"<UserLog(id={self.id}, action={self.action})>"


class GroupMessage(Base):
    """Все сообщения из групп для анализа (хранятся 24 часа)"""
    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    telegram_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    matched_keyword: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Если нашлось ключевое слово
    matched_city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Если нашёлся город
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    user: Mapped["User"] = relationship("User", back_populates="group_messages")
    group: Mapped["Group"] = relationship("Group")

    def __repr__(self) -> str:
        return f"<GroupMessage(id={self.id}, matched={self.matched_keyword is not None})>"


class BotSettings(Base):
    """Глобальные настройки бота (редактируются из админки)"""
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<BotSettings(key={self.key})>"


# Дефолтные ключевые слова убраны - пользователи добавляют свои
DEFAULT_KEYWORDS = []

# Текст помощи по умолчанию
DEFAULT_HELP_TEXT = """📚 <b>Справка по боту</b>

<b>📋 Список групп</b> - выберите группы, в которых бот будет искать заказы

<b>🔤 Ключевые слова</b> - слова, по которым бот определяет заказы (заказ, трансфер, такси и т.д.)

<b>🏙 Города</b> - добавьте города, чтобы бот искал заказы только по ним

<b>▶️ Мониторинг</b> - включите/выключите отслеживание заказов

<b>💳 Подписка</b> - оформите или продлите подписку

❓ Остались вопросы? Напишите в поддержку."""
