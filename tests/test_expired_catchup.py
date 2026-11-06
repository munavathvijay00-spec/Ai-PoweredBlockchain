"""Regression coverage for deliberate free-tier expired-backlog recovery.

These tests use fake transactions only; they do not contact RPC or modify Neon.
"""
from contextlib import asynccontextmanager
import pytest

from src.ingest.expired_catchup import (
    MIN_BACKLOG_BLOCKS,
    choose_expired_anchor,
    jump_past_expired_history,
)

H1 = "0x" + "1" * 64
H2 = "0x" + "2" * 64


class FakeClient:
    def __init__(self):
        self.calls = []
    async def get_block(self, block_number, *, full_transactions):
        self.calls.append((block_number, full_transactions))
        if block_number == 1000 - 36:
            return {"number": block_number, "hash": H2, "parentHash": H1, "timestamp": 100}
        if block_number == 1000 - 37:
            return {"number": block_number, "hash": H1, "parentHash": H1, "timestamp": 90}
        raise AssertionError(f"unexpected block: {block_number}")


class FakeDb:
    def __init__(self):
        self.commands = []
    @asynccontextmanager
    async def transaction(self):
        self.commands.append(("start",))
        try:
            yield
            self.commands.append(("commit",))
        except Exception:
            self.commands.append(("rollback",))
            raise
    async def execute(self, query, *args):
        self.commands.append((query, *args))


def test_anchor_only_for_large_backlog():
    assert choose_expired_anchor(600, 1000) == 964
    assert choose_expired_anchor(1000 - MIN_BACKLOG_BLOCKS + 1, 1000) is None
    assert choose_expired_anchor(None, 1000) is None
    assert choose_expired_anchor(1000, 1000) is None


@pytest.mark.asyncio
async def test_unexpired_anchor_never_skips(monkeypatch):
    client, db = FakeClient(), FakeDb()
    result = await jump_past_expired_history(
        db, client, 600, 1000,
        is_expired=lambda *args, **kw: False,
    )
    assert result is None
    assert not db.commands
    assert client.calls == [(964, False)]


@pytest.mark.asyncio
async def test_expired_gap_commits_atomically(monkeypatch):
    import src.ingest.expired_catchup as target

    async def lineage(db, header):
        db.commands.append(("lineage", header["number"]))
    async def cursor(db, block, block_hash):
        db.commands.append(("checkpoint", block, block_hash))

    monkeypatch.setattr(target, "record_lineage", lineage)
    monkeypatch.setattr(target, "save_cursor_checkpoint", cursor)
    db, client = FakeDb(), FakeClient()
    result = await jump_past_expired_history(
        db, client, 600, 1000,
        is_expired=lambda header, **kw: header["timestamp"] < 120,
    )
    assert result == (964, H2)
    assert db.commands[0] == ("start",)
    assert db.commands[-1] == ("commit",)
    gap = next(x for x in db.commands if "INSERT INTO ingest_coverage_gaps" in x[0])
    assert gap[1:] == (601, 963, 964, H2, "Expired live-window history skipped during free-tier recovery; not indexed.")
    assert ("lineage", 964) in db.commands
    assert ("checkpoint", 964, H2) in db.commands


@pytest.mark.asyncio
async def test_mismatched_parent_fails_closed():
    client, db = FakeClient(), FakeDb()
    async def inconsistent(block, *, full_transactions):
        return {"number": block, "hash": H2 if block == 964 else H1,
                "parentHash": H2, "timestamp": 100}
    client.get_block = inconsistent
    with pytest.raises(RuntimeError, match="LINEAGE_CONFLICT"):
        await jump_past_expired_history(
            db, client, 600, 1000,
            is_expired=lambda *args, **kwargs: True,
        )
    assert not db.commands
