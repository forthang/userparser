from flask import Blueprint, render_template, request
from flask_login import login_required

from admin import db

users_bp = Blueprint('users', __name__)


@users_bp.route('/')
@login_required
def users_list():
    filter_type = request.args.get('filter', 'all')
    search = request.args.get('search', '')

    users = db.get_all_users(filter_type=filter_type, search=search if search else None)

    return render_template('users.html',
                           users=users,
                           filter_type=filter_type,
                           search=search)


@users_bp.route('/<int:user_id>')
@login_required
def user_detail(user_id):
    user = db.get_user_by_id(user_id)
    if not user:
        return render_template('error.html', message='User not found'), 404

    groups = db.get_user_groups(user_id)
    keywords = db.get_user_keywords(user_id)
    cities = db.get_user_cities(user_id)
    payments = db.get_user_payments(user_id)
    orders = db.get_user_orders(user_id, limit=50)
    logs = db.get_user_logs(user_id, limit=100)

    msg_filter = request.args.get('msg_filter', 'all')
    messages = db.get_user_messages(user_id, filter_type=msg_filter)

    return render_template('user_detail.html',
                           user=user,
                           groups=groups,
                           keywords=keywords,
                           cities=cities,
                           payments=payments,
                           orders=orders,
                           logs=logs,
                           messages=messages,
                           msg_filter=msg_filter)
