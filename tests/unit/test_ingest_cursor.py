"""Persistent cursor query contract."""
import pytest
from unittest.mock import AsyncMock
from src.ingest.cursor import ensure_cursor_schema, load_cursor, save_cursor


@pytest.mark.asyncio
async def test_load_missing_cursor():
    db = AsyncMock()
    db.fetchval.return_value = None
    assert await load_cursor(db) is None


@pytest.mark.asyncio
async def test_load_existing_cursor():
    db = AsyncMock()
    db.fetchval.return_value = 26176000
    assert await load_cursor(db) == 26176000


@pytest.mark.asyncio
async def test_save_cursor_is_monotonic():
    db = AsyncMock()
    await save_cursor(db, 123)
    sql = db.execute.await_args.args[0]
    assert "GREATEST" in sql
    assert db.execute.await_args.args[-1] == 123


@pytest.mark.asyncio
async def test_schema_is_bounded():
    db = AsyncMock()
    await ensure_cursor_schema(db)
    statements = [call.args[0] for call in db.execute.await_args_list]
    assert any("PRIMARY KEY" in sql for sql in statements)
    assert any("ADD COLUMN IF NOT EXISTS block_hash" in sql for sql in statements)
