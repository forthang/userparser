import hashlib
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from bot.config import config

logger = logging.getLogger(__name__)


class RobokassaPayment:
    """Сервис для работы с платежами Robokassa"""

    # URLs Робокассы
    PAYMENT_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"
    PAYMENT_URL_TEST = "https://auth.robokassa.ru/Merchant/Index.aspx"

    @staticmethod
    def _generate_signature(*args) -> str:
        """Генерирует MD5 подпись для Робокассы"""
        signature_string = ":".join(str(arg) for arg in args)
        return hashlib.md5(signature_string.encode()).hexdigest()

    @staticmethod
    async def create_payment(
        amount: float,
        user_id: int,
        invoice_id: int,
        description: str = "Подписка на бота",
    ) -> Optional[Dict[str, Any]]:
        """
        Создает ссылку на оплату через Робокассу.

        Args:
            amount: Сумма платежа
            user_id: Telegram ID пользователя
            invoice_id: Уникальный номер счета (можно использовать payment.id из БД)
            description: Описание платежа

        Returns:
            Dict с payment_url и invoice_id или None при ошибке
        """
        try:
            merchant_login = config.robokassa.merchant_login
            password1 = config.robokassa.password1

            if not merchant_login or not password1:
                logger.error("Robokassa credentials not configured")
                return None

            # Форматируем сумму (2 знака после запятой)
            out_sum = f"{amount:.2f}"

            # Генерируем подпись: MerchantLogin:OutSum:InvId:Password1
            signature = RobokassaPayment._generate_signature(
                merchant_login,
                out_sum,
                invoice_id,
                password1
            )

            # Формируем параметры
            params = {
                "MerchantLogin": merchant_login,
                "OutSum": out_sum,
                "InvId": invoice_id,
                "Description": description,
                "SignatureValue": signature,
                "IsTest": 1 if config.robokassa.test_mode else 0,
                # Дополнительные параметры (Shp_) для идентификации пользователя
                "Shp_user_id": user_id,
            }

            # Формируем URL для оплаты
            payment_url = f"{RobokassaPayment.PAYMENT_URL}?{urlencode(params)}"

            return {
                "payment_url": payment_url,
                "invoice_id": invoice_id,
                "status": "pending",
            }

        except Exception as e:
            logger.error(f"Error creating Robokassa payment: {e}")
            return None

    @staticmethod
    def verify_result_signature(
        out_sum: str,
        inv_id: str,
        signature: str,
        shp_user_id: str = None,
    ) -> bool:
        """
        Проверяет подпись от Робокассы (для Result URL webhook).

        Формат подписи: MD5(OutSum:InvId:Password2[:Shp_параметры])
        Shp_ параметры добавляются в алфавитном порядке.
        """
        try:
            password2 = config.robokassa.password2

            # Формируем строку для подписи
            if shp_user_id:
                # Если есть Shp_ параметры, они добавляются в алфавитном порядке
                expected_signature = RobokassaPayment._generate_signature(
                    out_sum,
                    inv_id,
                    password2,
                    f"Shp_user_id={shp_user_id}"
                )
            else:
                expected_signature = RobokassaPayment._generate_signature(
                    out_sum,
                    inv_id,
                    password2
                )

            return signature.lower() == expected_signature.lower()

        except Exception as e:
            logger.error(f"Error verifying Robokassa signature: {e}")
            return False

    @staticmethod
    def verify_success_signature(
        out_sum: str,
        inv_id: str,
        signature: str,
        shp_user_id: str = None,
    ) -> bool:
        """
        Проверяет подпись для Success URL (страница успешной оплаты).

        Формат подписи: MD5(OutSum:InvId:Password1[:Shp_параметры])
        """
        try:
            password1 = config.robokassa.password1

            if shp_user_id:
                expected_signature = RobokassaPayment._generate_signature(
                    out_sum,
                    inv_id,
                    password1,
                    f"Shp_user_id={shp_user_id}"
                )
            else:
                expected_signature = RobokassaPayment._generate_signature(
                    out_sum,
                    inv_id,
                    password1
                )

            return signature.lower() == expected_signature.lower()

        except Exception as e:
            logger.error(f"Error verifying Robokassa success signature: {e}")
            return False

    @staticmethod
    def is_configured() -> bool:
        """Проверяет, настроена ли Робокасса"""
        return bool(
            config.robokassa.merchant_login and
            config.robokassa.password1 and
            config.robokassa.password2
        )
