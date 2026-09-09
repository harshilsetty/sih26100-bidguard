import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from app.core.config import settings

logger = logging.getLogger(__name__)

# Base declarative class
Base = declarative_base()

is_sqlite = "sqlite" in settings.DATABASE_URL
engine_kwargs = {"echo": False, "future": True}
if not is_sqlite:
    engine_kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})

# Async database engine
engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database extensions and create tables, with automatic SQLite fallback if PostgreSQL is offline."""
    global engine, AsyncSessionLocal
    current_is_sqlite = "sqlite" in settings.DATABASE_URL
    try:
        async with engine.begin() as conn:
            if not current_is_sqlite:
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                except Exception as ext_err:
                    logger.warning(f"Could not enable PostgreSQL extensions: {ext_err}")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully.")
    except Exception as e:
        err_str = str(e).lower()
        if not current_is_sqlite and ("refused" in err_str or "1225" in err_str or "connection" in err_str):
            logger.warning(
                f"PostgreSQL connection refused ({e}). Falling back to local SQLite database (gem_compliance.db)..."
            )
            sqlite_url = "sqlite+aiosqlite:///gem_compliance.db"
            engine = create_async_engine(sqlite_url, echo=False, future=True)
            AsyncSessionLocal = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Local SQLite database initialized successfully for zero-configuration local execution.")
        else:
            logger.warning(f"Database initialization warning: {e}")
