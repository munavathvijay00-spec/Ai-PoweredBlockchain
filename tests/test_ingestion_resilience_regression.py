"""Fail-closed ingestion health and checkpoint tests.

These tests use fake DBs; they never modify a live checkpoint.
"""
import pytest
from src.ingest.cursor import validate_block_hash, save_cursor_checkpoint, rewind_cursor_checkpoint
from src.ingest.health_monitor import assess_ingestion_health
from src.ingest.loop import next_blocks, block_outside_live_retention, is_chain_integrity_failure

HASH_A = "0x" + "a" * 64
HASH_B = "0x" + "b" * 64


class FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.query = None
        self.args = None

    async def fetchrow(self, query, *args):
        self.query = query
        self.args = args
        return self.row


def test_block_hash_rejects_invalid_values():
    for item in ["", "0x123", "a" * 64, "0x" + "z" * 64, None]:
        with pytest.raises(ValueError):
            validate_block_hash(item)
    validate_block_hash(HASH_A)


@pytest.mark.asyncio
async def test_checkpoint_rejects_nonadvancing_result():
    db = FakeDB(None)
    with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
        await save_cursor_checkpoint(db, 100, HASH_A)
    assert "ingest_cursor.last_block < EXCLUDED.last_block" in db.query


@pytest.mark.asyncio
async def test_reorg_rewind_is_compare_and_swap_and_fails_closed():
    db = FakeDB(None)
    with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
        await rewind_cursor_checkpoint(
            db,
            expected_block=110, expected_hash=HASH_A,
            ancestor_block=108, ancestor_hash=HASH_B,
        )
    assert "last_block = $2" in db.query
    assert "lower(block_hash) = lower($3)" in db.query


@pytest.mark.asyncio
async def test_reorg_rewind_rejects_forward_ancestor():
    with pytest.raises(ValueError, match="ancestor"):
        await rewind_cursor_checkpoint(
            FakeDB(), expected_block=100, expected_hash=HASH_A,
            ancestor_block=100, ancestor_hash=HASH_B,
        )


def test_restart_from_checkpoint_processes_successors_only():
    assert next_blocks(100, 103, limit=3) == [101, 102, 103]
    assert next_blocks(103, 103, limit=3) == []
    assert next_blocks(None, 103, limit=3) == [103]


def test_integrity_conflicts_are_not_silently_retried():
    for code in ["REORG_DETECTED:", "CHECKPOINT_CONFLICT:", "LINEAGE_CONFLICT:"]:
        assert is_chain_integrity_failure(RuntimeError(code))
    assert not is_chain_integrity_failure(TimeoutError("RPC unavailable"))


def test_stale_data_is_not_live():
    status = assess_ingestion_health(250, 200)
    assert status["lag_blocks"] == 50
    assert status["warning"] is True
    assert block_outside_live_retention({"timestamp": 1000}, now_ts=1400, retention_minutes=5)
