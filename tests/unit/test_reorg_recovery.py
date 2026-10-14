import pytest

from src.ingest.reorg import _verified_common_ancestor, transaction_hashes


def tx_hash(char):
    return "0x" + char * 64


def block(height, hash_char, tx_chars):
    return {
        "number": height,
        "hash": tx_hash(hash_char),
        "parentHash": tx_hash("f"),
        "transactions": [{"hash": tx_hash(char)} for char in tx_chars],
    }


class FakeClient:
    def __init__(self, blocks):
        self.blocks = blocks

    async def get_block(self, height, full_transactions=False):
        return self.blocks[height]


class FakeDb:
    def __init__(self, stored, lineage=None):
        self.stored = stored
        self.lineage = lineage or {}

    async def fetchrow(self, query, height):
        value = self.lineage.get(height)
        if value is None:
            return None
        return {"block_hash": value[0], "transaction_count": value[1]}

    async def fetch(self, query, height):
        return [{"hash": value.lower()} for value in self.stored.get(height, [])]


def test_transaction_hashes_reject_duplicate_membership():
    with pytest.raises(ValueError, match="duplicate"):
        transaction_hashes(block(10, "a", ["1", "1"]))


@pytest.mark.asyncio
async def test_bootstrap_finds_exact_transaction_membership_ancestor():
    blocks = {
        99: block(99, "9", ["1", "2"]),
        98: block(98, "8", ["3", "4"]),
    }
    db = FakeDb({99: [tx_hash("x")], 98: [tx_hash("3"), tx_hash("4")]})
    result = await _verified_common_ancestor(db, FakeClient(blocks), 100, 2)
    assert result == (98, tx_hash("8"), "exact_transaction_membership")


@pytest.mark.asyncio
async def test_lineage_hash_is_preferred_as_ancestor_proof():
    blocks = {99: block(99, "9", ["1"])}
    db = FakeDb({}, lineage={99: (tx_hash("9"), 1)})
    result = await _verified_common_ancestor(db, FakeClient(blocks), 100, 1)
    assert result == (99, tx_hash("9"), "lineage_hash")


@pytest.mark.asyncio
async def test_empty_block_membership_does_not_bootstrap_ancestor():
    blocks = {99: block(99, "9", [])}
    result = await _verified_common_ancestor(FakeDb({99: []}), FakeClient(blocks), 100, 1)
    assert result is None
