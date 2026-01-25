import os
import json
import asyncio
from flask import Blueprint, request, jsonify
from flask_login import login_required

from admin import db

actions_bp = Blueprint('actions', __name__)


def get_bot_token():
    """Get bot token from environment"""
    return os.getenv('BOT_TOKEN', '')


async def send_telegram_message(chat_id: int, message: str):
    """Send message via Telegram Bot API"""
    import aiohttp
    token = get_bot_token()
    if not token:
        return False, "BOT_TOKEN not configured"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            result = await resp.json()
            if result.get('ok'):
                return True, "Message sent"
            return False, result.get('description', 'Unknown error')


@actions_bp.route('/users/<int:user_id>/extend-subscription', methods=['POST'])
@login_required
def extend_subscription(user_id):
    days = request.json.get('days', 30) if request.is_json else 30
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if db.extend_subscription(user_id, days):
        db.add_user_log(user_id, 'subscription_extended', json.dumps({'days': days, 'by': 'admin'}))
        return jsonify({'success': True, 'message': f'Subscription extended by {days} days'})
    return jsonify({'success': False, 'error': 'Failed to extend subscription'}), 500


@actions_bp.route('/users/<int:user_id>/send-message', methods=['POST'])
@login_required
def send_message(user_id):
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400

    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Add reply instruction
    full_message = f"{message}\n\n<i>Ответить: /reply ваш текст</i>"

    # Send via Telegram
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success, result = loop.run_until_complete(
            send_telegram_message(user.telegram_id, full_message)
        )
    finally:
        loop.close()

    if success:
        db.add_user_log(user_id, 'admin_message_sent', json.dumps({'message': message}))
        return jsonify({'success': True, 'message': 'Message sent'})
    return jsonify({'success': False, 'error': result}), 500


@actions_bp.route('/users/<int:user_id>/reset-session', methods=['POST'])
@login_required
def reset_session(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if db.reset_session(user_id):
        db.add_user_log(user_id, 'session_reset', json.dumps({'by': 'admin'}))
        return jsonify({'success': True, 'message': 'Session reset successfully'})
    return jsonify({'success': False, 'error': 'Failed to reset session'}), 500


@actions_bp.route('/users/<int:user_id>/ban', methods=['POST'])
@login_required
def ban_user(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if db.toggle_ban(user_id, True):
        db.add_user_log(user_id, 'banned', json.dumps({'by': 'admin'}))
        return jsonify({'success': True, 'message': 'User banned'})
    return jsonify({'success': False, 'error': 'Failed to ban user'}), 500


@actions_bp.route('/users/<int:user_id>/unban', methods=['POST'])
@login_required
def unban_user(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if db.toggle_ban(user_id, False):
        db.add_user_log(user_id, 'unbanned', json.dumps({'by': 'admin'}))
        return jsonify({'success': True, 'message': 'User unbanned'})
    return jsonify({'success': False, 'error': 'Failed to unban user'}), 500


@actions_bp.route('/users/<int:user_id>/toggle-monitoring', methods=['POST'])
@login_required
def toggle_monitoring(user_id):
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400

    enabled = request.json.get('enabled', False)
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if db.toggle_monitoring(user_id, enabled):
        action = 'monitoring_enabled' if enabled else 'monitoring_disabled'
        db.add_user_log(user_id, action, json.dumps({'by': 'admin'}))
        return jsonify({'success': True, 'message': f'Monitoring {"enabled" if enabled else "disabled"}'})
    return jsonify({'success': False, 'error': 'Failed to toggle monitoring'}), 500
