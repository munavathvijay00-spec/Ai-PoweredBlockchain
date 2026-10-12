"""Repository must reject missing address IDs instead of silently losing transfers."""
import pytest
from unittest.mock import AsyncMock
from src.database.repositories import TransactionRepository


@pytest.mark.asyncio
async def test_missing_address_mapping_refuses_batch_before_write():
    db = AsyncMock()
    repo = TransactionRepository(db, None)
    tx = {
        "hash": "0x" + "a" * 64,
        "from_address": "0x" + "b" * 40,
        "to_address": "0x" + "c" * 40,
        "value": 1, "block_number": 1, "timestamp": None,
    }
    with pytest.raises(ValueError, match="Missing address mapping"):
        await repo.bulk_create_transactions([tx], {tx["from_address"]: 1})
    db.execute.assert_not_awaited()
