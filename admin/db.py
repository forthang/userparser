import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy import create_engine, select, delete, update, String, or_, cast
from sqlalchemy.orm import sessionmaker, joinedload

from bot.database.models import (
    User, Group, Keyword, City, Payment, Order,
    UserLog, GroupMessage, Base
)

# Database URL
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'taxi_parser')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session():
    """Context manager for database sessions"""
    session = Session()
    try:
        yield session
        session.commit()
        # Detach all objects from session so they can be used after close
        session.expunge_all()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create tables if they don't exist"""
    Base.metadata.create_all(engine)


# ============ User operations ============

def get_all_users(filter_type: str = 'all', search: str = None):
    """Get all users with optional filters"""
    with get_session() as session:
        query = select(User).order_by(User.created_at.desc())

        if filter_type == 'with_subscription':
            query = query.where(User.subscription_end > datetime.utcnow())
        elif filter_type == 'without_subscription':
            query = query.where(
                (User.subscription_end <= datetime.utcnow()) |
                (User.subscription_end.is_(None))
            )
        elif filter_type == 'banned':
            query = query.where(User.is_banned == True)
        elif filter_type == 'monitoring':
            query = query.where(User.monitoring_enabled == True)

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    User.username.ilike(search_term),
                    User.phone.ilike(search_term),
                    cast(User.telegram_id, String).ilike(search_term)
                )
            )

        result = session.execute(query)
        return list(result.scalars().all())


def get_user_by_id(user_id: int):
    """Get user by internal ID"""
    with get_session() as session:
        return session.get(User, user_id)


def get_user_details(user_id: int):
    """Get user with all related data"""
    with get_session() as session:
        user = session.execute(
            select(User)
            .options(
                joinedload(User.groups),
                joinedload(User.keywords),
                joinedload(User.cities),
                joinedload(User.payments),
            )
            .where(User.id == user_id)
        ).unique().scalar_one_or_none()
        return user


def get_user_groups(user_id: int):
    """Get user's groups"""
    with get_session() as session:
        result = session.execute(
            select(Group)
            .where(Group.user_id == user_id)
            .order_by(Group.is_enabled.desc(), Group.group_name)
        )
        return list(result.scalars().all())


def get_user_keywords(user_id: int):
    """Get user's keywords"""
    with get_session() as session:
        result = session.execute(
            select(Keyword)
            .where(Keyword.user_id == user_id)
            .order_by(Keyword.word)
        )
        return list(result.scalars().all())


def get_user_cities(user_id: int):
    """Get user's cities"""
    with get_session() as session:
        result = session.execute(
            select(City)
            .where(City.user_id == user_id)
            .order_by(City.city_name)
        )
        return list(result.scalars().all())


def get_user_payments(user_id: int):
    """Get user's payments"""
    with get_session() as session:
        result = session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())


def get_user_orders(user_id: int, limit: int = 100):
    """Get user's orders"""
    with get_session() as session:
        result = session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ============ User logs ============

def get_user_logs(user_id: int, limit: int = 100):
    """Get user's action logs"""
    with get_session() as session:
        result = session.execute(
            select(UserLog)
            .where(UserLog.user_id == user_id)
            .order_by(UserLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


def add_user_log(user_id: int, action: str, details: str = None):
    """Add user log entry"""
    with get_session() as session:
        log = UserLog(user_id=user_id, action=action, details=details)
        session.add(log)
        session.commit()
        return log


# ============ Group messages ============

def get_user_messages(user_id: int, filter_type: str = 'all', limit: int = 500):
    """Get user's group messages from last 24 hours"""
    threshold = datetime.utcnow() - timedelta(hours=24)
    with get_session() as session:
        query = select(GroupMessage).options(
            joinedload(GroupMessage.group)
        ).where(
            GroupMessage.user_id == user_id,
            GroupMessage.created_at >= threshold
        )

        if filter_type == 'matched':
            query = query.where(GroupMessage.matched_keyword.isnot(None))
        elif filter_type == 'unmatched':
            query = query.where(GroupMessage.matched_keyword.is_(None))

        result = session.execute(
            query.order_by(GroupMessage.created_at.desc()).limit(limit)
        )
        return list(result.unique().scalars().all())


# ============ Statistics ============

def get_statistics():
    """Get overall statistics"""
    with get_session() as session:
        all_users = session.execute(select(User)).scalars().all()

        now = datetime.utcnow()
        return {
            'total': len(all_users),
            'active': len([u for u in all_users if u.is_active]),
            'with_subscription': len([u for u in all_users if u.subscription_end and u.subscription_end > now]),
            'monitoring': len([u for u in all_users if u.monitoring_enabled]),
            'banned': len([u for u in all_users if u.is_banned]),
            'no_session': len([u for u in all_users if not u.session_string and u.is_active]),
        }


def get_problem_users():
    """Get users with problems"""
    with get_session() as session:
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        # Users with expired subscription but still active
        expired = session.execute(
            select(User).where(
                User.is_active == True,
                User.subscription_end.isnot(None),
                User.subscription_end <= now
            ).limit(20)
        ).scalars().all()

        # Users without session but with subscription
        no_session = session.execute(
            select(User).where(
                User.is_active == True,
                User.session_string.is_(None),
                User.subscription_end > now
            ).limit(20)
        ).scalars().all()

        # Users with recent errors
        recent_errors = session.execute(
            select(UserLog)
            .where(
                UserLog.action.like('%error%'),
                UserLog.created_at >= week_ago
            )
            .order_by(UserLog.created_at.desc())
            .limit(20)
        ).scalars().all()

        error_user_ids = [log.user_id for log in recent_errors]
        with_errors = []
        if error_user_ids:
            with_errors = session.execute(
                select(User).where(User.id.in_(error_user_ids))
            ).scalars().all()

        return {
            'expired_subscription': expired,
            'no_session': no_session,
            'with_errors': with_errors,
        }


# ============ Admin actions ============

def extend_subscription(user_id: int, days: int = 30):
    """Extend user subscription"""
    with get_session() as session:
        user = session.get(User, user_id)
        if user:
            if user.subscription_end and user.subscription_end > datetime.utcnow():
                user.subscription_end = user.subscription_end + timedelta(days=days)
            else:
                user.subscription_end = datetime.utcnow() + timedelta(days=days)
            user.is_active = True
            session.commit()
            return True
    return False


def reset_session(user_id: int):
    """Reset user session"""
    with get_session() as session:
        user = session.get(User, user_id)
        if user:
            user.session_string = None
            user.monitoring_enabled = False
            session.commit()
            return True
    return False


def toggle_ban(user_id: int, ban: bool):
    """Ban or unban user"""
    with get_session() as session:
        user = session.get(User, user_id)
        if user:
            user.is_banned = ban
            if ban:
                user.monitoring_enabled = False
            session.commit()
            return True
    return False


def toggle_monitoring(user_id: int, enabled: bool):
    """Enable or disable monitoring"""
    with get_session() as session:
        user = session.get(User, user_id)
        if user:
            user.monitoring_enabled = enabled
            session.commit()
            return True
    return False
