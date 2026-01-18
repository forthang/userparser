import logging
import uuid
from typing import Optional, Dict, Any
from yookassa import Configuration, Payment
from yookassa.domain.response import PaymentResponse

from bot.config import config

logger = logging.getLogger(__name__)

Configuration.account_id = config.yukassa.shop_id
Configuration.secret_key = config.yukassa.secret_key


class YukassaPayment:
    @staticmethod
    async def create_payment(
        amount: float,
        user_id: int,
        description: str = "Подписка на бота",
        return_url: str = "https://t.me/your_bot",
    ) -> Optional[Dict[str, Any]]:
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
                "confirmation_url": payment.confirmation.confirmation_url,
                "status": payment.status,
            }

        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return None

    @staticmethod
    async def check_payment(payment_id: str) -> Optional[Dict[str, Any]]:
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
            logger.error(f"Error checking payment: {e}")
            return None

    @staticmethod
    def is_payment_successful(status: str) -> bool:
        return status == "succeeded"


class PaymentManager:
    def __init__(self):
        self.pending_payments: Dict[int, str] = {}

    def add_pending(self, user_id: int, payment_id: str):
        self.pending_payments[user_id] = payment_id

    def get_pending(self, user_id: int) -> Optional[str]:
        return self.pending_payments.get(user_id)

    def remove_pending(self, user_id: int):
        if user_id in self.pending_payments:
            del self.pending_payments[user_id]


payment_manager = PaymentManager()
