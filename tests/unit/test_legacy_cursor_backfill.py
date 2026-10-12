"""Legacy cursor hash backfill must never rewrite an existing checkpoint."""
import pytest
from unittest.mock import AsyncMock
from src.ingest.cursor import backfill_cursor_hash


@pytest.mark.asyncio
async def test_backfill_updates_only_null_hash_at_exact_height():
    db = AsyncMock()
    expected = "0x" + "a" * 64
    db.fetchrow.return_value = {"block_hash": expected}
    assert await backfill_cursor_hash(db, 123, expected) == expected
    sql = db.fetchrow.await_args.args[0]
    assert "last_block = $2" in sql
    assert "block_hash IS NULL" in sql
    assert "UPDATE ingest_cursor" in sql


@pytest.mark.asyncio
async def test_conflicting_checkpoint_fails_closed():
    db = AsyncMock()
    db.fetchrow.return_value = None
    with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
        await backfill_cursor_hash(db, 123, "0x" + "b" * 64)


@pytest.mark.asyncio
async def test_bad_hash_rejected_before_sql():
    db = AsyncMock()
    with pytest.raises(ValueError, match="32-byte"):
        await backfill_cursor_hash(db, 123, "0xdead")
    db.fetchrow.assert_not_awaited()
