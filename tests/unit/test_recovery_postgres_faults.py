"""Checkpoint fault tests using GitHub Actions' disposable PostgreSQL database.

These tests must never connect to a production DB. Temp tables shadow only the
current test connection, and the configured DB name must end with '_test'.
"""

import asyncio
import os
import time
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


class TransientFailureRPC:
    def __init__(self, failures):
        self.remaining = failures
        self.attempts = 0

    async def get_block(self, height, *, full_transactions=False):
        self.attempts += 1
        if self.remaining:
            self.remaining -= 1
            raise ConnectionError("isolated simulated RPC outage")
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


@pytest.mark.asyncio
async def test_postgres_checkpoint_survives_rpc_outage_and_recovers():
    """Real PostgreSQL checkpoint; simulated RPC failure; actual elapsed time.

    This measures the isolated retry drill, NOT Render restart or live RPC uptime.
    """
    conn = await safe_test_connection()
    try:
        await save_cursor_checkpoint(conn, 100, HASH_A)
        await save_cursor_checkpoint(conn, 101, HASH_B)
        rpc = TransientFailureRPC(failures=2)
        started = time.perf_counter()
        for attempt in range(3):
            try:
                outcome = await reconcile_competing_worker(conn, rpc, 100)
                break
            except ConnectionError:
                # Shortened delay solely for CI; never interpret as production MTTR.
                await asyncio.sleep(0.02)
        else:
            pytest.fail("checkpoint did not recover after the transient RPC outage")
        elapsed = time.perf_counter() - started
        assert outcome == (101, HASH_B)
        assert rpc.attempts == 3
        assert elapsed >= 0.04
        assert await load_cursor_checkpoint(conn) == (101, HASH_B)
    finally:
        await conn.close()
