"""Duplicate hashes with contradictory native transfer facts must fail closed."""
import pytest
from unittest.mock import AsyncMock
from src.database.repositories import TransactionRepository


def tx():
    return {
        "hash": "0x" + "a" * 64,
        "from_address": "0x" + "b" * 40,
        "to_address": "0x" + "c" * 40,
        "value": 7, "block_number": 123, "timestamp": None,
    }


@pytest.mark.asyncio
async def test_conflicting_duplicate_hash_aborts_before_insert():
    db = AsyncMock()
    item = tx()
    db.fetch.return_value = [{
        "hash": item["hash"], "block_number": 122,
        "from_address_id": 1, "to_address_id": 2, "value": 7,
    }]
    repo = TransactionRepository(db, None)
    mapping = {item["from_address"]: 1, item["to_address"]: 2}
    with pytest.raises(RuntimeError, match="TRANSACTION_PROVENANCE_CONFLICT"):
        await repo.bulk_create_transactions([item], mapping)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_duplicate_hash_is_allowed_as_idempotent_retry():
    db = AsyncMock()
    item = tx()
    db.fetch.return_value = [{
        "hash": item["hash"], "block_number": 123,
        "from_address_id": 1, "to_address_id": 2, "value": 7,
    }]
    db.execute.return_value = "INSERT 0 0"
    repo = TransactionRepository(db, None)
    mapping = {item["from_address"]: 1, item["to_address"]: 2}
    assert await repo.bulk_create_transactions([item], mapping) == 0
