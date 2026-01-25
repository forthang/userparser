import os
from flask_login import UserMixin


class User(UserMixin):
    """Simple admin user for Flask-Login"""

    def __init__(self):
        self.id = 'admin'

    @staticmethod
    def check_password(password: str) -> bool:
        """Check if password matches ADMIN_PASSWORD from env"""
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if not admin_password:
            return False
        return password == admin_password
