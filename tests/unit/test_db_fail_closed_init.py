"""Failed PostgreSQL startup must not leave a disconnected global singleton."""
import pytest
from unittest.mock import AsyncMock, patch
import src.database.connection as connection


@pytest.mark.asyncio
async def test_get_db_rejects_failed_connection_and_allows_retry():
    original = connection._db
    connection._db = None
    try:
        with patch.object(connection, "Database") as cls:
            candidate = cls.return_value
            candidate.connect = AsyncMock(return_value=False)
            candidate.close = AsyncMock()
            with pytest.raises(RuntimeError, match="PostgreSQL"):
                await connection.get_db()
            candidate.close.assert_awaited_once()
            assert connection._db is None
    finally:
        connection._db = original


@pytest.mark.asyncio
async def test_get_db_publishes_only_connected_pool():
    original = connection._db
    connection._db = None
    try:
        with patch.object(connection, "Database") as cls:
            candidate = cls.return_value
            candidate.connect = AsyncMock(return_value=True)
            candidate.pool = object()
            assert await connection.get_db() is candidate
            assert connection._db is candidate
    finally:
        connection._db = original
