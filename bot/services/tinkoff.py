import hashlib
import logging
import aiohttp
from typing import Optional, Dict, Any

from bot.config import config

logger = logging.getLogger(__name__)


class TinkoffPayment:
    """Сервис для работы с платежами Тинькофф Касса (T-Pay)"""

    # API URL (тестовый режим определяется терминалом с суффиксом DEMO)
    API_URL = "https://securepay.tinkoff.ru/v2"

    @staticmethod
    def _get_api_url() -> str:
        """Возвращает URL API"""
        return TinkoffPayment.API_URL

    @staticmethod
    def _generate_token(params: dict) -> str:
        """
        Генерирует токен для подписи запроса.

        Алгоритм:
        1. Добавить Password (секретный ключ) в параметры
        2. Отсортировать по ключу
        3. Конкатенировать значения
        4. SHA256 хеш
        """
        # Копируем параметры и добавляем секретный ключ
        sign_params = {k: v for k, v in params.items() if v is not None}
        sign_params["Password"] = config.tinkoff.secret_key

        # Сортируем по ключу и конкатенируем значения
        sorted_params = sorted(sign_params.items())
        concatenated = "".join(str(v) for k, v in sorted_params)

        # SHA256
        return hashlib.sha256(concatenated.encode()).hexdigest()

    @staticmethod
    async def create_payment(
        amount: float,
        user_id: int,
        order_id: str,
        description: str = "Подписка на бота",
    ) -> Optional[Dict[str, Any]]:
        """
        Создает платеж через Тинькофф Кассу.

        Args:
            amount: Сумма в рублях
            user_id: Telegram ID пользователя
            order_id: Уникальный ID заказа
            description: Описание платежа

        Returns:
            Dict с payment_url и payment_id или None при ошибке
        """
        try:
            terminal_key = config.tinkoff.terminal_key

            if not terminal_key or not config.tinkoff.secret_key:
                logger.error("Tinkoff credentials not configured")
                return None

            # Сумма в копейках
            amount_kopeks = int(amount * 100)

            params = {
                "TerminalKey": terminal_key,
                "Amount": amount_kopeks,
                "OrderId": order_id,
                "Description": description,
                "DATA": {
                    "user_id": str(user_id),
                },
            }

            # Генерируем токен (без вложенных объектов)
            token_params = {
                "TerminalKey": terminal_key,
                "Amount": amount_kopeks,
                "OrderId": order_id,
                "Description": description,
            }
            params["Token"] = TinkoffPayment._generate_token(token_params)

            api_url = TinkoffPayment._get_api_url()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{api_url}/Init",
                    json=params,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    result = await response.json()

                    if result.get("Success"):
                        return {
                            "payment_id": result.get("PaymentId"),
                            "payment_url": result.get("PaymentURL"),
                            "status": "pending",
                        }
                    else:
                        logger.error(f"Tinkoff Init error: {result.get('Message')} ({result.get('ErrorCode')})")
                        return None

        except Exception as e:
            logger.error(f"Error creating Tinkoff payment: {e}")
            return None

    @staticmethod
    async def check_payment(payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Проверяет статус платежа в Тинькофф.

        Args:
            payment_id: ID платежа от Тинькофф

        Returns:
            Dict со статусом платежа
        """
        try:
            terminal_key = config.tinkoff.terminal_key

            params = {
                "TerminalKey": terminal_key,
                "PaymentId": payment_id,
            }
            params["Token"] = TinkoffPayment._generate_token(params)

            api_url = TinkoffPayment._get_api_url()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{api_url}/GetState",
                    json=params,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    result = await response.json()

                    if result.get("Success"):
                        status = result.get("Status", "UNKNOWN")
                        return {
                            "payment_id": payment_id,
                            "status": status,
                            "paid": status == "CONFIRMED",
                            "amount": result.get("Amount", 0) / 100,  # Из копеек в рубли
                        }
                    else:
                        logger.error(f"Tinkoff GetState error: {result.get('Message')}")
                        return None

        except Exception as e:
            logger.error(f"Error checking Tinkoff payment: {e}")
            return None

    @staticmethod
    def is_payment_successful(status: str) -> bool:
        """
        Проверяет, успешен ли платеж.

        Статусы Тинькофф:
        - CONFIRMED - платеж подтвержден
        - AUTHORIZED - платеж авторизован (для двухстадийной оплаты)
        """
        return status in ("CONFIRMED", "AUTHORIZED")

    @staticmethod
    def verify_notification(params: dict) -> bool:
        """
        Проверяет подпись уведомления от Тинькофф (webhook).

        Args:
            params: Параметры из уведомления

        Returns:
            True если подпись верна
        """
        try:
            received_token = params.pop("Token", None)
            if not received_token:
                return False

            expected_token = TinkoffPayment._generate_token(params)
            return received_token.lower() == expected_token.lower()

        except Exception as e:
            logger.error(f"Error verifying Tinkoff notification: {e}")
            return False

    @staticmethod
    def is_configured() -> bool:
        """Проверяет, настроена ли Тинькофф Касса"""
        return bool(
            config.tinkoff.terminal_key and
            config.tinkoff.secret_key
        )
