"""Tests for the lightweight in-place schema-upgrade path in init_db."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from src.storage.database import Base, init_db


@pytest.mark.asyncio
async def test_init_db_creates_new_columns_on_fresh_db(tmp_path):
    """A fresh DB should end up with all model columns, including ones added later."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/fresh.db"
    await init_db(db_url)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        cols_documents = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("documents")}
        )
        cols_messages = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("messages")}
        )
        cols_jobs = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("ingestion_jobs")}
        )
    await engine.dispose()

    assert "tags" in cols_documents
    for col in (
        "model_used",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "thinking_tokens",
    ):
        assert col in cols_messages, f"missing {col} after init_db"
    for col in ("prompt_tokens", "completion_tokens"):
        assert col in cols_jobs, f"missing ingestion_jobs.{col} after init_db"


@pytest.mark.asyncio
async def test_init_db_is_idempotent_when_columns_already_exist(tmp_path):
    """Running init_db twice should not error or duplicate columns."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/idempotent.db"
    await init_db(db_url)
    await init_db(db_url)  # Should be a no-op for the upgrade additions.

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        cols_messages = await conn.run_sync(
            lambda c: [col["name"] for col in inspect(c).get_columns("messages")]
        )
    await engine.dispose()

    # Each column should appear exactly once.
    assert cols_messages.count("thinking_tokens") == 1


@pytest.mark.asyncio
async def test_init_db_upgrades_legacy_schema_in_place(tmp_path):
    """Simulate a pre-S7 DB (no tags / token columns) and assert init_db adds them."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/legacy.db"

    # Build a legacy schema by hand, omitting the new columns.
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE collections ("
            "  id VARCHAR(36) PRIMARY KEY, name VARCHAR(255), description TEXT,"
            "  created_at DATETIME, updated_at DATETIME"
            ")"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE documents ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  collection_id VARCHAR(36),"
            "  filename VARCHAR(500),"
            "  status VARCHAR(20)"
            ")"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE conversations ("
            "  id VARCHAR(36) PRIMARY KEY, collection_id VARCHAR(36), title VARCHAR(255),"
            "  created_at DATETIME, updated_at DATETIME"
            ")"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE messages ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  conversation_id VARCHAR(36),"
            "  role VARCHAR(20),"
            "  content TEXT,"
            "  sources TEXT,"
            "  created_at DATETIME"
            ")"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE ingestion_jobs ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  document_id VARCHAR(36),"
            "  status VARCHAR(20),"
            "  parser VARCHAR(50),"
            "  chunk_size INTEGER,"
            "  chunk_overlap INTEGER,"
            "  contextual_enrichment BOOLEAN,"
            "  error_message TEXT,"
            "  started_at DATETIME,"
            "  completed_at DATETIME,"
            "  created_at DATETIME"
            ")"
        )
    await engine.dispose()

    # Now run init_db — it should add the new columns to existing tables.
    await init_db(db_url)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        cols_documents = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("documents")}
        )
        cols_messages = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("messages")}
        )
        cols_jobs = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("ingestion_jobs")}
        )
    await engine.dispose()

    assert "tags" in cols_documents
    assert "thinking_tokens" in cols_messages
    assert "prompt_tokens" in cols_messages
    assert "model_used" in cols_messages
    assert "prompt_tokens" in cols_jobs
    assert "completion_tokens" in cols_jobs


# Suppress the unused import warning in CI; Base is needed for the side-effect
# of registering models so init_db's create_all can do its thing.
_ = Base
