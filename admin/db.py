import os
import psycopg2
from datetime import datetime, timedelta
from contextlib import contextmanager
from sqlalchemy import create_engine, select, delete, update, String, or_, cast
from sqlalchemy.orm import sessionmaker, joinedload

from bot.database.models import (
    User, Group, Keyword, City, Payment, Order,
    UserLog, GroupMessage, Base,
    MonitorWorker, GroupAssignment, SharedGroupMessage, OrderDelivery
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


def get_db_connection():
    """Get raw psycopg2 connection for webhook handlers"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


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


# ============ Shared Pool operations ============

def get_all_workers():
    """Get all monitor workers"""
    with get_session() as session:
        result = session.execute(
            select(MonitorWorker).order_by(MonitorWorker.name)
        )
        return list(result.scalars().all())


def get_worker_by_id(worker_id: int):
    """Get worker by ID"""
    with get_session() as session:
        return session.get(MonitorWorker, worker_id)


def get_worker_assignments(worker_id: int):
    """Get groups assigned to worker"""
    with get_session() as session:
        result = session.execute(
            select(GroupAssignment)
            .where(GroupAssignment.worker_id == worker_id)
            .order_by(GroupAssignment.group_name)
        )
        return list(result.scalars().all())


def get_all_group_assignments():
    """Get all group assignments with worker info"""
    with get_session() as session:
        result = session.execute(
            select(GroupAssignment, MonitorWorker)
            .join(MonitorWorker, GroupAssignment.worker_id == MonitorWorker.id)
            .order_by(GroupAssignment.group_name)
        )
        return [(a, w) for a, w in result.fetchall()]


def create_worker(name: str, session_string: str, phone: str = None, max_groups: int = 50):
    """Create new monitor worker"""
    with get_session() as session:
        worker = MonitorWorker(
            name=name,
            session_string=session_string,
            phone=phone,
            max_groups=max_groups,
        )
        session.add(worker)
        session.commit()
        return worker


def update_worker(worker_id: int, **kwargs):
    """Update worker fields"""
    with get_session() as session:
        worker = session.get(MonitorWorker, worker_id)
        if worker:
            for key, value in kwargs.items():
                if hasattr(worker, key):
                    setattr(worker, key, value)
            session.commit()
            return True
    return False


def delete_worker(worker_id: int):
    """Delete worker"""
    with get_session() as session:
        result = session.execute(
            delete(MonitorWorker).where(MonitorWorker.id == worker_id)
        )
        session.commit()
        return result.rowcount > 0


def get_shared_pool_stats():
    """Get shared pool statistics"""
    with get_session() as session:
        workers = session.execute(select(MonitorWorker)).scalars().all()

        stats = {
            'total_workers': len(workers),
            'active_workers': len([w for w in workers if w.is_active]),
            'workers_with_errors': len([w for w in workers if w.last_error]),
            'workers': [],
        }

        for worker in workers:
            assignments = session.execute(
                select(GroupAssignment)
                .where(GroupAssignment.worker_id == worker.id)
            ).scalars().all()

            stats['workers'].append({
                'id': worker.id,
                'name': worker.name,
                'phone': worker.phone,
                'is_active': worker.is_active,
                'groups_count': len(assignments),
                'max_groups': worker.max_groups,
                'last_error': worker.last_error,
                'last_active_at': worker.last_active_at,
            })

        stats['total_groups'] = sum(w['groups_count'] for w in stats['workers'])
        return stats


# ============ Shared Group Messages (Chat History) ============

def get_monitored_groups():
    """Get list of all monitored groups with stats"""
    with get_session() as session:
        threshold = datetime.utcnow() - timedelta(hours=24)

        # Get unique groups from assignments
        assignments = session.execute(
            select(GroupAssignment, MonitorWorker)
            .join(MonitorWorker, GroupAssignment.worker_id == MonitorWorker.id)
            .where(GroupAssignment.is_active == True)
        ).fetchall()

        groups = []
        for assignment, worker in assignments:
            # Count messages
            msg_count = session.execute(
                select(SharedGroupMessage)
                .where(
                    SharedGroupMessage.telegram_group_id == assignment.telegram_group_id,
                    SharedGroupMessage.created_at >= threshold
                )
            ).scalars().all()

            # Count deliveries (orders sent to users)
            msg_ids = [m.id for m in msg_count]
            deliveries_count = 0
            if msg_ids:
                deliveries = session.execute(
                    select(OrderDelivery)
                    .where(OrderDelivery.shared_message_id.in_(msg_ids))
                ).scalars().all()
                deliveries_count = len(deliveries)

            groups.append({
                'telegram_group_id': assignment.telegram_group_id,
                'group_name': assignment.group_name,
                'worker_id': worker.id,
                'worker_name': worker.name,
                'messages_24h': len(msg_count),
                'orders_sent': deliveries_count,
            })

        return groups


def get_group_chat_history(telegram_group_id: int, limit: int = 500):
    """Get chat history for a specific group"""
    with get_session() as session:
        threshold = datetime.utcnow() - timedelta(hours=24)

        messages = session.execute(
            select(SharedGroupMessage)
            .where(
                SharedGroupMessage.telegram_group_id == telegram_group_id,
                SharedGroupMessage.created_at >= threshold
            )
            .order_by(SharedGroupMessage.created_at.desc())
            .limit(limit)
        ).scalars().all()

        result = []
        for msg in messages:
            # Get deliveries for this message
            deliveries = session.execute(
                select(OrderDelivery, User)
                .join(User, OrderDelivery.user_id == User.id)
                .where(OrderDelivery.shared_message_id == msg.id)
            ).fetchall()

            result.append({
                'id': msg.id,
                'message_id': msg.message_id,
                'message_text': msg.message_text,
                'sender_id': msg.sender_id,
                'sender_username': msg.sender_username,
                'created_at': msg.created_at,
                'deliveries': [
                    {
                        'user_id': user.id,
                        'telegram_id': user.telegram_id,
                        'username': user.username,
                        'keyword': delivery.matched_keyword,
                        'city': delivery.matched_city,
                    }
                    for delivery, user in deliveries
                ]
            })

        return result


def get_group_info(telegram_group_id: int):
    """Get info about a specific group"""
    with get_session() as session:
        assignment = session.execute(
            select(GroupAssignment, MonitorWorker)
            .join(MonitorWorker, GroupAssignment.worker_id == MonitorWorker.id)
            .where(GroupAssignment.telegram_group_id == telegram_group_id)
        ).first()

        if not assignment:
            return None

        group_assignment, worker = assignment

        # Count users monitoring this group
        users = session.execute(
            select(User, Group)
            .join(Group, User.id == Group.user_id)
            .where(
                Group.telegram_group_id == telegram_group_id,
                Group.is_enabled == True,
                User.monitoring_enabled == True
            )
        ).fetchall()

        return {
            'telegram_group_id': telegram_group_id,
            'group_name': group_assignment.group_name,
            'worker_id': worker.id,
            'worker_name': worker.name,
            'users_monitoring': [
                {'id': user.id, 'telegram_id': user.telegram_id, 'username': user.username}
                for user, group in users
            ],
        }


# ============ Order Deliveries ============

def get_recent_deliveries(limit: int = 100):
    """Get recent order deliveries"""
    with get_session() as session:
        threshold = datetime.utcnow() - timedelta(hours=24)

        result = session.execute(
            select(OrderDelivery, SharedGroupMessage, User)
            .join(SharedGroupMessage, OrderDelivery.shared_message_id == SharedGroupMessage.id)
            .join(User, OrderDelivery.user_id == User.id)
            .where(OrderDelivery.delivered_at >= threshold)
            .order_by(OrderDelivery.delivered_at.desc())
            .limit(limit)
        ).fetchall()

        return [
            {
                'id': delivery.id,
                'user_id': user.id,
                'telegram_id': user.telegram_id,
                'username': user.username,
                'group_name': msg.group_name,
                'telegram_group_id': msg.telegram_group_id,
                'keyword': delivery.matched_keyword,
                'city': delivery.matched_city,
                'message_text': msg.message_text[:200] + '...' if len(msg.message_text) > 200 else msg.message_text,
                'delivered_at': delivery.delivered_at,
            }
            for delivery, msg, user in result
        ]
