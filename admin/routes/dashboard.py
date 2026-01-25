from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required

from admin.auth import User as AdminUser
from admin import db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if AdminUser.check_password(password):
            user = AdminUser()
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.dashboard'))
        flash('Invalid password', 'error')
    return render_template('login.html')


@dashboard_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('dashboard.login'))


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    stats = db.get_statistics()
    problems = db.get_problem_users()
    return render_template('dashboard.html', stats=stats, problems=problems)
