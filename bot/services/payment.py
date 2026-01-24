import logging
import uuid
from enum import Enum
from typing import Optional, Dict, Any
from yookassa import Configuration, Payment
from yookassa.domain.response import PaymentResponse

from bot.config import config
from bot.services.robokassa import RobokassaPayment
from bot.services.tinkoff import TinkoffPayment

logger = logging.getLogger(__name__)

# Инициализация ЮКассы
if config.yukassa.shop_id and config.yukassa.secret_key:
    Configuration.account_id = config.yukassa.shop_id
    Configuration.secret_key = config.yukassa.secret_key


class PaymentSystem(str, Enum):
    """Доступные платежные системы"""
    YUKASSA = "yukassa"
    ROBOKASSA = "robokassa"
    TINKOFF = "tinkoff"
    DISABLED = "disabled"


class YukassaPayment:
    """Сервис для работы с платежами ЮКасса"""

    @staticmethod
    async def create_payment(
        amount: float,
        user_id: int,
        description: str = "Подписка на бота",
        return_url: str = "https://t.me/your_bot",
    ) -> Optional[Dict[str, Any]]:
        """Создает платеж через ЮКассу"""
        try:
            idempotence_key = str(uuid.uuid4())

            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": str(user_id),
                }
            }, idempotence_key)

            return {
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "status": payment.status,
            }

        except Exception as e:
            logger.error(f"Error creating YuKassa payment: {e}")
            return None

    @staticmethod
    async def check_payment(payment_id: str) -> Optional[Dict[str, Any]]:
        """Проверяет статус платежа в ЮКассе"""
        try:
            payment: PaymentResponse = Payment.find_one(payment_id)

            return {
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": float(payment.amount.value),
                "metadata": payment.metadata,
            }

        except Exception as e:
            logger.error(f"Error checking YuKassa payment: {e}")
            return None

    @staticmethod
    def is_payment_successful(status: str) -> bool:
        """Проверяет, успешен ли платеж"""
        return status == "succeeded"

    @staticmethod
    def is_configured() -> bool:
        """Проверяет, настроена ли ЮКасса"""
        return bool(config.yukassa.shop_id and config.yukassa.secret_key)


class PaymentService:
    """
    Единый сервис для работы с платежами.
    Выбирает платежную систему на основе настроек из БД.
    """

    # Ключи настроек в БД
    SETTING_PAYMENT_SYSTEM = "payment_system"
    SETTING_SUBSCRIPTION_PRICE = "subscription_price"
    SETTING_SUBSCRIPTION_DAYS = "subscription_days"

    @staticmethod
    def get_default_system() -> PaymentSystem:
        """Возвращает платежную систему по умолчанию на основе конфигурации"""
        if YukassaPayment.is_configured():
            return PaymentSystem.YUKASSA
        elif RobokassaPayment.is_configured():
            return PaymentSystem.ROBOKASSA
        elif TinkoffPayment.is_configured():
            return PaymentSystem.TINKOFF
        return PaymentSystem.DISABLED

    @staticmethod
    async def create_payment(
        system: PaymentSystem,
        amount: float,
        user_id: int,
        invoice_id: int,
        description: str = "Подписка на бота",
        return_url: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Создает платеж через выбранную платежную систему.

        Returns:
            Dict с ключами:
            - payment_id: ID платежа (для ЮКассы) или invoice_id (для Робокассы)
            - payment_url: Ссылка на оплату
            - status: Статус платежа
        """
        if system == PaymentSystem.YUKASSA:
            result = await YukassaPayment.create_payment(
                amount=amount,
                user_id=user_id,
                description=description,
                return_url=return_url or "https://t.me/your_bot",
            )
            if result:
                result["system"] = PaymentSystem.YUKASSA.value
            return result

        elif system == PaymentSystem.ROBOKASSA:
            result = await RobokassaPayment.create_payment(
                amount=amount,
                user_id=user_id,
                invoice_id=invoice_id,
                description=description,
            )
            if result:
                result["payment_id"] = str(invoice_id)
                result["system"] = PaymentSystem.ROBOKASSA.value
            return result

        elif system == PaymentSystem.TINKOFF:
            result = await TinkoffPayment.create_payment(
                amount=amount,
                user_id=user_id,
                order_id=str(invoice_id),
                description=description,
            )
            if result:
                result["system"] = PaymentSystem.TINKOFF.value
            return result

        else:
            logger.error(f"Unknown or disabled payment system: {system}")
            return None

    @staticmethod
    async def check_payment(
        system: PaymentSystem,
        payment_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверяет статус платежа.

        Для ЮКассы и Тинькофф - запрос к API.
        Для Робокассы - проверка через webhook (Result URL).
        """
        if system == PaymentSystem.YUKASSA:
            return await YukassaPayment.check_payment(payment_id)
        elif system == PaymentSystem.TINKOFF:
            return await TinkoffPayment.check_payment(payment_id)
        elif system == PaymentSystem.ROBOKASSA:
            # Робокасса подтверждается через webhook
            # Здесь можно только вернуть что платеж ожидает
            return {
                "payment_id": payment_id,
                "status": "pending",
                "message": "Проверка через webhook",
            }
        return None

    @staticmethod
    def is_payment_successful(system: PaymentSystem, status: str) -> bool:
        """Проверяет, успешен ли платеж"""
        if system == PaymentSystem.YUKASSA:
            return YukassaPayment.is_payment_successful(status)
        elif system == PaymentSystem.ROBOKASSA:
            return status == "confirmed"
        elif system == PaymentSystem.TINKOFF:
            return TinkoffPayment.is_payment_successful(status)
        return False

    @staticmethod
    def get_available_systems() -> list:
        """Возвращает список доступных (настроенных) платежных систем"""
        systems = []
        if YukassaPayment.is_configured():
            systems.append(PaymentSystem.YUKASSA)
        if RobokassaPayment.is_configured():
            systems.append(PaymentSystem.ROBOKASSA)
        if TinkoffPayment.is_configured():
            systems.append(PaymentSystem.TINKOFF)
        return systems


class PaymentManager:
    """Менеджер для отслеживания ожидающих платежей"""

    def __init__(self):
        self.pending_payments: Dict[int, Dict[str, Any]] = {}

    def add_pending(
        self,
        user_id: int,
        payment_id: str,
        system: PaymentSystem,
        db_payment_id: int = None,
    ):
        """Добавляет платеж в список ожидающих"""
        self.pending_payments[user_id] = {
            "payment_id": payment_id,
            "system": system,
            "db_payment_id": db_payment_id,
        }

    def get_pending(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию об ожидающем платеже"""
        return self.pending_payments.get(user_id)

    def remove_pending(self, user_id: int):
        """Удаляет платеж из списка ожидающих"""
        if user_id in self.pending_payments:
            del self.pending_payments[user_id]


# Глобальный менеджер платежей
payment_manager = PaymentManager()
