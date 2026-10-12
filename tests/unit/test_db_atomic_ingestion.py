"""Database transaction routing and rollback contract."""
import pytest
from unittest.mock import AsyncMock
from src.database.connection import Database


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.rolled_back = exc_type is not None
        self.conn.committed = exc_type is None


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.rolled_back = False
        self.committed = False

    def transaction(self):
        return FakeTransaction(self)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"


class FakePool:
    def __init__(self, conn):
        self.conn = conn
        self.acquisitions = 0

    def acquire(self):
        pool = self
        class Acquire:
            async def __aenter__(self):
                pool.acquisitions += 1
                return pool.conn
            async def __aexit__(self, exc_type, exc, tb):
                return False
        return Acquire()


def database():
    db = Database.__new__(Database)
    from contextvars import ContextVar
    db._transaction_connection = ContextVar('test_db_transaction', default=None)
    conn = FakeConnection()
    db.pool = FakePool(conn)
    return db, conn


@pytest.mark.asyncio
async def test_multiple_writes_use_one_connection_and_commit():
    db, conn = database()
    async with db.transaction():
        await db.execute('INSERT tx')
        await db.execute('UPDATE cursor')
    assert db.pool.acquisitions == 1
    assert len(conn.executed) == 2
    assert conn.committed is True


@pytest.mark.asyncio
async def test_error_rolls_back_and_resets_context():
    db, conn = database()
    with pytest.raises(ValueError):
        async with db.transaction():
            await db.execute('INSERT tx')
            raise ValueError('cursor failed')
    assert conn.rolled_back is True
    await db.execute('outside transaction')
    assert db.pool.acquisitions == 2


@pytest.mark.asyncio
async def test_nested_transactions_rejected():
    db, _ = database()
    with pytest.raises(RuntimeError, match='Nested'):
        async with db.transaction():
            async with db.transaction():
                pass
