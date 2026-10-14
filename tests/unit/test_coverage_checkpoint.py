"""Coverage endpoint must distinguish reorg recovery from historical completeness."""
import pytest
from unittest.mock import AsyncMock
from src.api.coverage_routes import get_coverage


@pytest.mark.asyncio
async def test_coverage_reports_hash_guard_without_claiming_full_history():
    repo = AsyncMock()
    repo.db.fetchrow.side_effect = [
        {"min_block": 100, "max_block": 101, "oldest_observed_at": None,
         "newest_observed_at": None, "stored_transactions": 1,
         "blocks_with_stored_transactions": 1},
        {"last_block": 101, "block_hash": "0x" + "a" * 64, "updated_at": None},
    ]
    response = await get_coverage(repo)
    verification = response["reorg_verification"]
    assert verification["status"] == "checkpoint_hash_recorded"
    assert verification["automatic_shallow_reorg_recovery"] is True
    assert verification["reorg_recovery_lineage_blocks"] >= 64
    assert verification["historical_completeness"] is False
    assert response["native_transactions"]["historical_completeness"] is False


@pytest.mark.asyncio
async def test_coverage_handles_missing_cursor_table():
    repo = AsyncMock()
    repo.db.fetchrow.side_effect = [
        {"min_block": None, "max_block": None, "oldest_observed_at": None,
         "newest_observed_at": None, "stored_transactions": 0,
         "blocks_with_stored_transactions": 0},
        RuntimeError("relation ingest_cursor does not exist"),
    ]
    response = await get_coverage(repo)
    assert response["reorg_verification"]["status"] == "not_verified"
