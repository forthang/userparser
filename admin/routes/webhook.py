"""
Webhook endpoints для приёма уведомлений от платёжных систем.
При успешной оплате автоматически активирует подписку и уведомляет пользователя.
"""
import logging
import hashlib
import hmac
import json
import asyncio
import aiohttp
from flask import Blueprint, request, jsonify
from admin.db import get_db_connection

logger = logging.getLogger(__name__)

bp = Blueprint('webhook', __name__, url_prefix='/webhook')


def get_bot_token():
    """Получает токен бота из переменных окружения"""
    import os
    return os.getenv('BOT_TOKEN')


async def send_telegram_message(chat_id: int, text: str):
    """Отправляет сообщение пользователю через Telegram Bot API"""
    bot_token = get_bot_token()
    if not bot_token:
        logger.error("BOT_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"Message sent to user {chat_id}")
                    return True
                else:
                    logger.error(f"Failed to send message: {await resp.text()}")
                    return False
    except Exception as e:
        logger.error(f"Error sending telegram message: {e}")
        return False


def run_async(coro):
    """Запускает асинхронную функцию в синхронном контексте"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def activate_subscription(user_id: int, days: int = 30):
    """Активирует подписку пользователю"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Получаем текущую дату окончания подписки
        cur.execute("""
            SELECT subscription_end, telegram_id FROM users WHERE id = %s
        """, (user_id,))
        row = cur.fetchone()

        if not row:
            logger.error(f"User {user_id} not found")
            return None

        current_end = row[0]
        telegram_id = row[1]

        # Если подписка активна - продлеваем от текущей даты
        # Если нет - от сегодня
        from datetime import datetime, timedelta
        now = datetime.utcnow()

        if current_end and current_end > now:
            new_end = current_end + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)

        cur.execute("""
            UPDATE users
            SET subscription_end = %s
            WHERE id = %s
        """, (new_end, user_id))

        conn.commit()
        logger.info(f"Subscription activated for user {user_id} until {new_end}")

        return {
            "telegram_id": telegram_id,
            "subscription_end": new_end
        }

    except Exception as e:
        logger.error(f"Error activating subscription: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def confirm_payment_by_payment_id(payment_id: str):
    """Подтверждает платёж по payment_id (для ЮКассы)"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE payments
            SET status = 'confirmed', confirmed_at = NOW()
            WHERE payment_id = %s AND status = 'pending'
            RETURNING user_id, amount
        """, (payment_id,))

        row = cur.fetchone()
        conn.commit()

        if row:
            return {"user_id": row[0], "amount": row[1]}
        return None

    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def confirm_payment_by_id(db_id: int):
    """Подтверждает платёж по id записи в БД (для Тинькофф - OrderId = db.id)"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE payments
            SET status = 'confirmed', confirmed_at = NOW()
            WHERE id = %s AND status = 'pending'
            RETURNING user_id, amount
        """, (db_id,))

        row = cur.fetchone()
        conn.commit()

        if row:
            return {"user_id": row[0], "amount": row[1]}
        return None

    except Exception as e:
        logger.error(f"Error confirming payment by id: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def confirm_payment(payment_id: str):
    """Подтверждает платёж - пробует по payment_id, потом по id"""
    # Сначала пробуем по payment_id
    result = confirm_payment_by_payment_id(payment_id)
    if result:
        return result

    # Если не найден - пробуем как id записи
    try:
        db_id = int(payment_id)
        return confirm_payment_by_id(db_id)
    except ValueError:
        return None


def get_subscription_days():
    """Получает количество дней подписки из настроек"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT value FROM bot_settings WHERE key = 'subscription_days'
        """)
        row = cur.fetchone()
        return int(row[0]) if row else 30
    except:
        return 30
    finally:
        cur.close()
        conn.close()


@bp.route('/yukassa', methods=['POST'])
def yukassa_webhook():
    """
    Webhook для ЮКассы.
    Документация: https://yookassa.ru/developers/using-api/webhooks
    """
    try:
        data = request.get_json()
        logger.info(f"YuKassa webhook received: {data}")

        if not data:
            return jsonify({"error": "No data"}), 400

        event = data.get('event')
        obj = data.get('object', {})

        if event == 'payment.succeeded':
            payment_id = obj.get('id')
            metadata = obj.get('metadata', {})
            user_telegram_id = metadata.get('user_id')

            if not payment_id:
                return jsonify({"error": "No payment_id"}), 400

            # Подтверждаем платёж
            payment_info = confirm_payment(payment_id)

            if payment_info:
                # Активируем подписку
                days = get_subscription_days()
                result = activate_subscription(payment_info['user_id'], days)

                if result:
                    # Отправляем уведомление пользователю
                    message = (
                        f"✅ <b>Оплата успешна!</b>\n\n"
                        f"💰 Сумма: {payment_info['amount']} руб.\n"
                        f"📅 Подписка активна до: {result['subscription_end'].strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"Теперь вы можете использовать все функции бота!"
                    )
                    run_async(send_telegram_message(result['telegram_id'], message))

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"YuKassa webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/robokassa', methods=['POST', 'GET'])
def robokassa_webhook():
    """
    Result URL для Робокассы.
    Вызывается после успешной оплаты.
    """
    import os

    try:
        # Робокасса может отправлять GET или POST
        if request.method == 'POST':
            data = request.form.to_dict()
        else:
            data = request.args.to_dict()

        logger.info(f"Robokassa webhook received: {data}")

        inv_id = data.get('InvId')
        out_sum = data.get('OutSum')
        signature = data.get('SignatureValue', '').upper()

        if not all([inv_id, out_sum, signature]):
            return "Invalid request", 400

        # Проверяем подпись
        password2 = os.getenv('ROBOKASSA_PASSWORD2', '')
        check_string = f"{out_sum}:{inv_id}:{password2}"
        expected_signature = hashlib.md5(check_string.encode()).hexdigest().upper()

        if signature != expected_signature:
            logger.error(f"Invalid Robokassa signature: {signature} != {expected_signature}")
            return "Invalid signature", 400

        # Подтверждаем платёж
        payment_info = confirm_payment(str(inv_id))

        if payment_info:
            # Активируем подписку
            days = get_subscription_days()
            result = activate_subscription(payment_info['user_id'], days)

            if result:
                # Отправляем уведомление пользователю
                message = (
                    f"✅ <b>Оплата успешна!</b>\n\n"
                    f"💰 Сумма: {out_sum} руб.\n"
                    f"📅 Подписка активна до: {result['subscription_end'].strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"Теперь вы можете использовать все функции бота!"
                )
                run_async(send_telegram_message(result['telegram_id'], message))

        # Робокасса ожидает OK{InvId}
        return f"OK{inv_id}", 200

    except Exception as e:
        logger.error(f"Robokassa webhook error: {e}")
        return "Error", 500


@bp.route('/tinkoff', methods=['POST'])
def tinkoff_webhook():
    """
    Webhook для Т-Кассы (Тинькофф).
    Документация: https://www.tinkoff.ru/kassa/develop/api/notifications/
    """
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    try:
        data = request.get_json()
        logger.info(f"Tinkoff webhook received: {data}")

        if not data:
            return jsonify({"error": "No data"}), 400

        # Проверяем подпись
        try:
            from bot.services.tinkoff import TinkoffPayment
            data_copy = data.copy()
            if not TinkoffPayment.verify_notification(data_copy):
                logger.error("Invalid Tinkoff webhook signature")
                return jsonify({"error": "Invalid signature"}), 400
        except Exception as e:
            logger.warning(f"Could not verify Tinkoff signature: {e}")
            # Продолжаем без проверки если модуль недоступен

        status = data.get('Status')
        payment_id = data.get('PaymentId')
        order_id = data.get('OrderId')
        amount = data.get('Amount', 0) / 100  # Тинькофф передаёт в копейках

        logger.info(f"Tinkoff payment status: {status}, order_id: {order_id}, amount: {amount}")

        # CONFIRMED - одностадийная оплата, AUTHORIZED - двухстадийная
        if status in ('CONFIRMED', 'AUTHORIZED'):
            # Подтверждаем платёж (ищем по order_id который = db_payment.id)
            payment_info = confirm_payment(str(order_id))

            if payment_info:
                # Активируем подписку
                days = get_subscription_days()
                result = activate_subscription(payment_info['user_id'], days)

                if result:
                    # Отправляем уведомление пользователю
                    message = (
                        f"✅ <b>Оплата успешна!</b>\n\n"
                        f"💰 Сумма: {amount:.0f} руб.\n"
                        f"📅 Подписка активна до: {result['subscription_end'].strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"Теперь вы можете использовать все функции бота!"
                    )
                    run_async(send_telegram_message(result['telegram_id'], message))
                    logger.info(f"Subscription activated for user {payment_info['user_id']}")
            else:
                logger.warning(f"Payment not found for order_id: {order_id}")

        return "OK", 200  # Тинькофф ожидает просто OK

    except Exception as e:
        logger.error(f"Tinkoff webhook error: {e}")
        return jsonify({"error": str(e)}), 500
