from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from bot.config import config
from bot.database.models import Base

engine = create_async_engine(
    config.database.url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Миграция: добавляем колонку response_text если её нет
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS response_text TEXT
                DEFAULT 'Я'
            """))
        except Exception:
            pass  # Колонка уже существует или другая ошибка


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
