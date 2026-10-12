"""Dashboard pagination contract: offset must reach SQL and the API response."""
import pytest
from unittest.mock import AsyncMock

from src.database.repositories import TransactionRepository


@pytest.mark.asyncio
async def test_recent_transactions_use_limit_and_offset():
    db = AsyncMock()
    db.fetch.return_value = []
    repo = TransactionRepository(db, AsyncMock())
    await repo.list_recent(limit=20, offset=40)
    sql, limit, offset = db.fetch.await_args.args
    assert "LIMIT $1 OFFSET $2" in sql
    assert "ORDER BY t.block_number DESC, t.id DESC" in sql
    assert (limit, offset) == (20, 40)


@pytest.mark.asyncio
async def test_recent_transactions_default_first_page():
    db = AsyncMock()
    db.fetch.return_value = []
    repo = TransactionRepository(db, AsyncMock())
    await repo.list_recent()
    assert db.fetch.await_args.args[-2:] == (10, 0)
