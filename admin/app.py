import os
import sys
from flask import Flask, redirect, url_for
from flask_login import LoginManager

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from admin.auth import User as AdminUser
from admin.routes.dashboard import dashboard_bp
from admin.routes.users import users_bp
from admin.routes.actions import actions_bp
from admin.routes.pool import bp as pool_bp
from admin.routes.webhook import bp as webhook_bp


def create_app():
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    app.secret_key = os.getenv('ADMIN_SECRET_KEY', os.getenv('ENCRYPTION_KEY', 'change-me-in-production'))

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'dashboard.login'
    login_manager.login_message = 'Please login to access admin panel'

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == 'admin':
            return AdminUser()
        return None

    # Register blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(actions_bp, url_prefix='/api')
    app.register_blueprint(pool_bp)
    app.register_blueprint(webhook_bp)  # /webhook/yukassa, /webhook/robokassa, /webhook/tinkoff

    @app.route('/')
    def index():
        return redirect(url_for('dashboard.dashboard'))

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('ADMIN_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'false').lower() == 'true')
