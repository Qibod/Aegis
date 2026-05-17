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

        # ── Migration 003: Risk Universe columns ──────────────────────────────
        # Idempotent column additions — safe on both fresh and existing DBs.
        for stmt in [
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS lob_id UUID REFERENCES lines_of_business(id) ON DELETE SET NULL",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS geography_ids UUID[] NOT NULL DEFAULT '{}'",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS product_ids UUID[] NOT NULL DEFAULT '{}'",
            "ALTER TABLE risks ADD COLUMN IF NOT EXISTS segment_ids UUID[] NOT NULL DEFAULT '{}'",
        ]:
            await conn.execute(text(stmt))

        # ── Migration 004: v2.1 Seeding / Validation / GRC Assistant ──────────
        # JSONB field-map columns on all 8 Company Profile entity tables.
        _profile_tables = [
            "org_profiles",
            "lines_of_business",
            "org_geographies",
            "org_industries",
            "org_products",
            "org_customer_segments",
            "org_third_parties",
            "org_data_tech_profiles",
        ]
        for tbl in _profile_tables:
            for col, default in [
                ("field_status_map",     "'{}'"),
                ("field_confidence_map", "'{}'"),
                ("field_source_map",     "'{}'"),
            ]:
                await conn.execute(text(
                    f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS "
                    f"{col} JSONB NOT NULL DEFAULT {default}"
                ))

        # Synthetic-tenant columns on organizations.
        for stmt in [
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS synthetic_proposals_pending INTEGER NOT NULL DEFAULT 0",
        ]:
            await conn.execute(text(stmt))

        # field_verification_state view (CREATE OR REPLACE is idempotent).
        await conn.execute(text("""
            CREATE OR REPLACE VIEW field_verification_state AS
            SELECT
                fv.org_id,
                fv.entity_type,
                fv.entity_id,
                fv.field_name,
                (
                    SELECT fv2.status FROM field_validations fv2
                    WHERE fv2.org_id = fv.org_id
                      AND fv2.entity_type = fv.entity_type
                      AND fv2.entity_id = fv.entity_id
                      AND fv2.field_name = fv.field_name
                      AND fv2.validator = 'A'
                    ORDER BY fv2.validated_at DESC LIMIT 1
                ) AS status_a,
                (
                    SELECT fv3.status FROM field_validations fv3
                    WHERE fv3.org_id = fv.org_id
                      AND fv3.entity_type = fv.entity_type
                      AND fv3.entity_id = fv.entity_id
                      AND fv3.field_name = fv.field_name
                      AND fv3.validator = 'B'
                    ORDER BY fv3.validated_at DESC LIMIT 1
                ) AS status_b,
                (
                    SELECT fv4.proposed_alternative FROM field_validations fv4
                    WHERE fv4.org_id = fv.org_id
                      AND fv4.entity_type = fv.entity_type
                      AND fv4.entity_id = fv.entity_id
                      AND fv4.field_name = fv.field_name
                      AND fv4.validator = 'B'
                    ORDER BY fv4.validated_at DESC LIMIT 1
                ) AS proposed_alternative,
                (
                    SELECT fv5.sources FROM field_validations fv5
                    WHERE fv5.org_id = fv.org_id
                      AND fv5.entity_type = fv.entity_type
                      AND fv5.entity_id = fv.entity_id
                      AND fv5.field_name = fv.field_name
                    ORDER BY fv5.validated_at DESC LIMIT 1
                ) AS latest_sources,
                (
                    SELECT fv6.validated_at FROM field_validations fv6
                    WHERE fv6.org_id = fv.org_id
                      AND fv6.entity_type = fv.entity_type
                      AND fv6.entity_id = fv.entity_id
                      AND fv6.field_name = fv.field_name
                    ORDER BY fv6.validated_at DESC LIMIT 1
                ) AS last_validated_at
            FROM field_validations fv
            GROUP BY fv.org_id, fv.entity_type, fv.entity_id, fv.field_name;
        """))


async def drop_tables() -> None:
    """Drop all tables — used in testing."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
