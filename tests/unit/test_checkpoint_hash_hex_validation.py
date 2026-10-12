"""Checkpoint hashes must be 32-byte hexadecimal, not merely 66 characters."""
import pytest
from unittest.mock import AsyncMock
from src.ingest.cursor import (
    validate_block_hash, save_cursor_checkpoint, backfill_cursor_hash,
)


def test_accepts_valid_hash():
    validate_block_hash("0x" + "aB" * 32)


@pytest.mark.parametrize("invalid", [
    "0x" + "g" * 64,
    "0x" + "z" * 64,
    "0x" + "a" * 63,
    "0X" + "a" * 64,
    None,
])
def test_rejects_invalid_hash(invalid):
    with pytest.raises(ValueError, match="hexadecimal"):
        validate_block_hash(invalid)


@pytest.mark.asyncio
async def test_rejects_invalid_checkpoint_before_database_write():
    db = AsyncMock()
    with pytest.raises(ValueError):
        await save_cursor_checkpoint(db, 123, "0x" + "g" * 64)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_invalid_legacy_backfill_before_database_write():
    db = AsyncMock()
    with pytest.raises(ValueError):
        await backfill_cursor_hash(db, 123, "0x" + "g" * 64)
    db.fetchrow.assert_not_awaited()
