"""Cursor advancement must not silently succeed when PostgreSQL rejects it."""
import pytest
from unittest.mock import AsyncMock
from src.ingest.cursor import save_cursor_checkpoint


HASH = "0x" + "a" * 64


@pytest.mark.asyncio
async def test_checkpoint_insert_or_advance_returns_saved_state():
    db = AsyncMock()
    db.fetchrow.return_value = {"last_block": 123, "block_hash": HASH}
    await save_cursor_checkpoint(db, 123, HASH)
    sql = db.fetchrow.await_args.args[0]
    assert "RETURNING last_block, block_hash" in sql
    assert "ingest_cursor.last_block < EXCLUDED.last_block" in sql


@pytest.mark.asyncio
async def test_rejected_checkpoint_advance_fails_closed():
    db = AsyncMock()
    db.fetchrow.return_value = None
    with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
        await save_cursor_checkpoint(db, 123, HASH)


@pytest.mark.asyncio
async def test_mismatched_returned_checkpoint_fails_closed():
    db = AsyncMock()
    db.fetchrow.return_value = {"last_block": 124, "block_hash": HASH}
    with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
        await save_cursor_checkpoint(db, 123, HASH)
