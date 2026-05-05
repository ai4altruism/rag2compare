"""SQLAlchemy async database setup and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings
from src.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# Columns added after the initial create_all schema. Listed here so dev
# databases get upgraded in-place without an Alembic migration step. Each
# entry is (table, column_name, sql_ddl_fragment). Adds are idempotent —
# we skip any column that already exists.
_LIGHTWEIGHT_UPGRADES: list[tuple[str, str, str]] = [
    ("documents", "tags", "JSON"),
    ("messages", "model_used", "VARCHAR(100)"),
    ("messages", "latency_ms", "INTEGER"),
    ("messages", "prompt_tokens", "INTEGER"),
    ("messages", "completion_tokens", "INTEGER"),
    ("messages", "thinking_tokens", "INTEGER"),
]


def get_engine(database_url: str | None = None):
    """Create the async database engine."""
    url = database_url or get_settings().database_url
    return create_async_engine(url, echo=False)


def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    engine = get_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


def _existing_columns(sync_conn, table: str) -> set[str]:
    insp = inspect(sync_conn)
    if not insp.has_table(table):
        return set()
    return {col["name"] for col in insp.get_columns(table)}


async def init_db(database_url: str | None = None) -> None:
    """Create tables and apply lightweight in-place column additions.

    `Base.metadata.create_all` is non-destructive but won't add new columns
    to existing tables, so we follow up with idempotent ALTER TABLE ADD
    COLUMN statements for nullable columns added after the initial schema.
    For non-trivial schema changes, switch to Alembic.
    """
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, column, ddl in _LIGHTWEIGHT_UPGRADES:
            existing = await conn.run_sync(_existing_columns, table)
            if not existing:
                continue  # Table didn't exist before create_all; columns are correct.
            if column in existing:
                continue
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
                )
                logger.info("schema_column_added", table=table, column=column)
            except Exception as e:  # pragma: no cover — best-effort upgrade
                logger.warning(
                    "schema_upgrade_failed",
                    table=table,
                    column=column,
                    error=str(e),
                )
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
