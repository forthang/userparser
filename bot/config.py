import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    token: str
    admin_ids: List[int]


@dataclass
class TelegramAPIConfig:
    api_id: int
    api_hash: str


@dataclass
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def url_sync(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class YukassaConfig:
    shop_id: str
    secret_key: str


@dataclass
class RobokassaConfig:
    merchant_login: str
    password1: str  # Для формирования подписи при создании платежа
    password2: str  # Для проверки подписи в Result URL
    test_mode: bool


@dataclass
class TinkoffConfig:
    terminal_key: str
    secret_key: str
    test_mode: bool


@dataclass
class SubscriptionConfig:
    price: int
    days: int


@dataclass
class Config:
    bot: BotConfig
    telegram_api: TelegramAPIConfig
    database: DatabaseConfig
    yukassa: YukassaConfig
    robokassa: RobokassaConfig
    tinkoff: TinkoffConfig
    subscription: SubscriptionConfig
    encryption_key: str
    response_text: str


def load_config() -> Config:
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

    return Config(
        bot=BotConfig(
            token=os.getenv("BOT_TOKEN", ""),
            admin_ids=admin_ids,
        ),
        telegram_api=TelegramAPIConfig(
            api_id=int(os.getenv("API_ID", "0")),
            api_hash=os.getenv("API_HASH", ""),
        ),
        database=DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=os.getenv("DB_NAME", "taxi_parser"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        ),
        yukassa=YukassaConfig(
            shop_id=os.getenv("YUKASSA_SHOP_ID", ""),
            secret_key=os.getenv("YUKASSA_SECRET_KEY", ""),
        ),
        robokassa=RobokassaConfig(
            merchant_login=os.getenv("ROBOKASSA_MERCHANT_LOGIN", ""),
            password1=os.getenv("ROBOKASSA_PASSWORD1", ""),
            password2=os.getenv("ROBOKASSA_PASSWORD2", ""),
            test_mode=os.getenv("ROBOKASSA_TEST_MODE", "true").lower() == "true",
        ),
        tinkoff=TinkoffConfig(
            terminal_key=os.getenv("TINKOFF_TERMINAL_KEY", ""),
            secret_key=os.getenv("TINKOFF_SECRET_KEY", ""),
            test_mode=os.getenv("TINKOFF_TEST_MODE", "true").lower() == "true",
        ),
        subscription=SubscriptionConfig(
            price=int(os.getenv("SUBSCRIPTION_PRICE", "1000")),
            days=int(os.getenv("SUBSCRIPTION_DAYS", "30")),
        ),
        encryption_key=os.getenv("ENCRYPTION_KEY", ""),
        response_text=os.getenv(
            "RESPONSE_TEXT",
            "Я"
        ),
    )


config = load_config()
