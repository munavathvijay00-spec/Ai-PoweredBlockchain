"""Fail-closed deployment overlap checkpoint recovery checks."""
import pytest
from src.ingest.checkpoint_reconcile import reconcile_competing_worker

HASH_A = "0x" + "a" * 64
HASH_B = "0x" + "b" * 64


class FakeDB:
    def __init__(self, height, hash_value):
        self.height, self.hash_value = height, hash_value
    async def fetchrow(self, query, *args):
        return {"last_block": self.height, "block_hash": self.hash_value}


class FakeClient:
    def __init__(self, height, hash_value):
        self.height, self.hash_value = height, hash_value
        self.calls = []
    async def get_block(self, height, *, full_transactions):
        self.calls.append((height, full_transactions))
        return {"number": self.height, "hash": self.hash_value}


@pytest.mark.asyncio
async def test_newer_canonical_checkpoint_resumes():
    client = FakeClient(106, HASH_B)
    winner = await reconcile_competing_worker(FakeDB(106, HASH_B), client, 100)
    assert winner == (106, HASH_B)
    assert client.calls == [(106, False)]


@pytest.mark.asyncio
async def test_stale_or_unanchored_checkpoint_does_not_resume():
    client = FakeClient(100, HASH_A)
    for height, hash_value in ((100, HASH_A), (99, HASH_A), (101, None)):
        assert await reconcile_competing_worker(FakeDB(height, hash_value), client, 100) is None
    assert client.calls == []


@pytest.mark.asyncio
async def test_noncanonical_competing_checkpoint_halts():
    with pytest.raises(RuntimeError, match="LINEAGE_CONFLICT"):
        await reconcile_competing_worker(FakeDB(106, HASH_A), FakeClient(106, HASH_B), 100)


@pytest.mark.asyncio
async def test_mismatched_competing_height_halts():
    with pytest.raises(RuntimeError, match="LINEAGE_CONFLICT"):
        await reconcile_competing_worker(FakeDB(106, HASH_B), FakeClient(105, HASH_B), 100)
