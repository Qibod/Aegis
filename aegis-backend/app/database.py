"""
app/database.py
───────────────
Async SQLAlchemy engine and session factory.
Uses asyncpg driver for full async PostgreSQL support.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import get_settings

settings = get_settings()


def _normalise_db_url(url: str) -> str:
    """
    Railway and most managed Postgres providers give a `postgresql://` URL.
    SQLAlchemy's async engine needs the asyncpg driver, so we coerce the
    scheme. Idempotent — leaves an already-correct URL alone.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    _normalise_db_url(settings.database_url),
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,       # test connections before use
    pool_recycle=3600,        # recycle connections every hour
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # prevent lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request.
    Session is committed on success, rolled back on exception.

    Usage:
        @router.get("/risks")
        async def list_risks(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager version for use outside FastAPI request cycle
    (e.g. Celery workers, startup scripts).

    Usage:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables and apply any idempotent column migrations."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent column additions for risk universe (safe on fresh and existing DBs)
        for stmt in [
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS lob_id UUID REFERENCES lines_of_business(id) ON DELETE SET NULL",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS geography_ids UUID[] NOT NULL DEFAULT '{}'",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS product_ids UUID[] NOT NULL DEFAULT '{}'",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS segment_ids UUID[] NOT NULL DEFAULT '{}'",
        ]:
            await conn.execute(text(stmt))


async def drop_tables() -> None:
    """Drop all tables — used in testing."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
