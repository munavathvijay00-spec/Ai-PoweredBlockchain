"""Checks that recent-activity SQL stays bounded before Python filtering."""
from unittest.mock import AsyncMock
import pytest

from src.risk.history_context import load_recent_activity


@pytest.mark.asyncio
async def test_history_query_limits_database_rows():
    db = type("DB", (), {})()
    db.fetch = AsyncMock(return_value=[])
    result = await load_recent_activity(
        db, ["0x" + "1" * 40], before_block=100, minutes=30, per_address=100
    )
    assert result == {}
    query, addresses, block, minutes, cap = db.fetch.await_args.args
    assert "LIMIT $4" in query
    assert addresses == ["0x" + "1" * 40]
    assert (block, minutes) == (100, 30)
    assert 0 < cap <= 50000


@pytest.mark.asyncio
async def test_history_query_caps_large_address_set():
    db = type("DB", (), {})()
    db.fetch = AsyncMock(return_value=[])
    await load_recent_activity(db, [f"0x{i:040x}" for i in range(500)], 100)
    assert db.fetch.await_args.args[-1] == 50000
