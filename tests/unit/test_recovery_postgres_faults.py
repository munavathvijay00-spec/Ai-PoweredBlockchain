"""Checkpoint fault tests using GitHub Actions' disposable PostgreSQL database.

These tests must never connect to a production DB. Temp tables shadow only the
current test connection, and the configured DB name must end with '_test'.
"""

import asyncio
import os
from urllib.parse import urlsplit

import asyncpg
import pytest

from src.ingest.cursor import load_cursor_checkpoint, save_cursor_checkpoint
from src.ingest.checkpoint_reconcile import reconcile_competing_worker


HASH_A = "0x" + "a" * 64
HASH_B = "0x" + "b" * 64


class CanonicalRPC:
    async def get_block(self, height, *, full_transactions=False):
        return {"number": height, "hash": HASH_B}


async def safe_test_connection():
    url = os.getenv("DATABASE_URL", "")
    if not url or not urlsplit(url).path.strip("/").endswith("_test"):
        pytest.skip("Requires an explicitly named disposable *_test Postgres database")
    conn = await asyncpg.connect(url)
    # Session-scoped temp table hides any table named ingest_cursor elsewhere.
    await conn.execute("""
        CREATE TEMP TABLE ingest_cursor (
            stream TEXT PRIMARY KEY,
            last_block BIGINT NOT NULL,
            block_hash TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        ) ON COMMIT PRESERVE ROWS
    """)
    return conn


@pytest.mark.asyncio
async def test_postgres_checkpoint_conflict_never_regresses_cursor():
    conn = await safe_test_connection()
    try:
        await save_cursor_checkpoint(conn, 100, HASH_A)
        await save_cursor_checkpoint(conn, 101, HASH_B)
        with pytest.raises(RuntimeError, match="CHECKPOINT_CONFLICT"):
            await save_cursor_checkpoint(conn, 100, HASH_A)
        assert await load_cursor_checkpoint(conn) == (101, HASH_B)
        assert await reconcile_competing_worker(conn, CanonicalRPC(), 100) == (101, HASH_B)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_postgres_interrupted_transaction_rolls_back_checkpoint():
    conn = await safe_test_connection()
    try:
        await save_cursor_checkpoint(conn, 100, HASH_A)

        async def interrupted_worker():
            async with conn.transaction():
                await save_cursor_checkpoint(conn, 101, HASH_B)
                raise asyncio.CancelledError("simulated interrupted worker")

        with pytest.raises(asyncio.CancelledError):
            await interrupted_worker()
        assert await load_cursor_checkpoint(conn) == (100, HASH_A)

        # A restarted worker can advance from the durable last committed state.
        await save_cursor_checkpoint(conn, 101, HASH_B)
        assert await load_cursor_checkpoint(conn) == (101, HASH_B)
    finally:
        await conn.close()
