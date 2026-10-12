"""A repeated transaction hash in one batch cannot silently overwrite transfer facts."""
import pytest
from unittest.mock import AsyncMock
from src.database.repositories import TransactionRepository


def item(value):
    return {
        "hash": "0x" + "a" * 64,
        "from_address": "0x" + "b" * 40,
        "to_address": "0x" + "c" * 40,
        "value": value,
        "block_number": 123,
        "timestamp": None,
    }


@pytest.mark.asyncio
async def test_contradictory_hash_within_batch_aborts_before_insert():
    db = AsyncMock()
    db.fetch.return_value = []
    mapping = {item(1)["from_address"]: 1, item(1)["to_address"]: 2}
    repo = TransactionRepository(db, None)
    with pytest.raises(RuntimeError, match="TRANSACTION_PROVENANCE_CONFLICT"):
        await repo.bulk_create_transactions([item(1), item(2)], mapping)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_hash_within_batch_is_not_silently_accepted():
    db = AsyncMock()
    db.fetch.return_value = []
    mapping = {item(1)["from_address"]: 1, item(1)["to_address"]: 2}
    repo = TransactionRepository(db, None)
    with pytest.raises(ValueError, match="Duplicate transaction hash"):
        await repo.bulk_create_transactions([item(1), item(1)], mapping)
    db.execute.assert_not_awaited()
