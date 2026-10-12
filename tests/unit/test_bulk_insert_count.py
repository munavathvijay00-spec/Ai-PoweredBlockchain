"""Bulk insert reports database-confirmed inserts, not candidate count."""
import pytest
from unittest.mock import AsyncMock
from src.database.repositories import TransactionRepository


def sample_tx(i):
    return {
        "hash": "0x" + format(i, "064x"),
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "value": 1, "block_number": 123, "timestamp": None,
    }


@pytest.mark.asyncio
async def test_bulk_insert_reports_actual_rows_with_conflicts():
    db = AsyncMock()
    db.execute.return_value = "INSERT 0 1"
    repo = TransactionRepository(db, None)
    addr_map = {"0x" + "a" * 40: 1, "0x" + "b" * 40: 2}
    assert await repo.bulk_create_transactions([sample_tx(1), sample_tx(2)], addr_map) == 1


@pytest.mark.asyncio
async def test_bulk_insert_rejects_invalid_database_count():
    db = AsyncMock()
    db.execute.return_value = "INSERT 0 3"
    repo = TransactionRepository(db, None)
    addr_map = {"0x" + "a" * 40: 1, "0x" + "b" * 40: 2}
    with pytest.raises(RuntimeError, match="Invalid inserted row count"):
        await repo.bulk_create_transactions([sample_tx(1)], addr_map)
