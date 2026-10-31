"""Historical evidence regression tests (no live provider or DB writes)."""
import pytest
from src.api.historical_routes import _evidence_key, _block_number, _contract_address, cached_wallet_history


class FakeDB:
    def __init__(self, rows, sync):
        self.rows, self.sync = rows, sync
    async def fetch(self, query, *args):
        return self.rows
    async def fetchval(self, query, *args):
        if "to_regclass" in query:
            return True
        return len(self.rows)
    async def fetchrow(self, query, *args):
        return self.sync


class Repo:
    def __init__(self, rows, sync):
        self.db = FakeDB(rows, sync)


def test_evidence_identity_deterministic():
    transfer = {"hash": "0x" + "a" * 64, "category": "erc20", "blockNum": "0x10"}
    assert _evidence_key(transfer, "incoming") == _evidence_key(dict(transfer), "incoming")
    assert _evidence_key(transfer, "outgoing") != _evidence_key(transfer, "incoming")


def test_block_and_contract_parse_conservatively():
    assert _block_number("0x10") == 16
    assert _block_number("bad") is None
    assert _contract_address({"rawContract": {"address": "invalid"}}) is None


@pytest.mark.asyncio
async def test_cached_history_replayability_and_count_mismatch():
    wallet = "0x" + "a" * 40
    records = [{"evidence_key": "example"}]
    sync = {"outgoing_complete": True, "incoming_complete": True, "records_cached": 2}
    output = await cached_wallet_history(wallet, limit=10, offset=0, repo=Repo(records, sync))
    assert output["total_cached"] == 1
    assert output["evidence_replayable_without_provider"] is True
    assert output["historical_complete_for_selected_categories"] is False
    assert output["cache_consistent_with_sync"] is False


@pytest.mark.asyncio
async def test_empty_cache_is_not_replayable():
    wallet = "0x" + "b" * 40
    output = await cached_wallet_history(wallet, limit=10, offset=0, repo=Repo([], None))
    assert output["total_cached"] == 0
    assert output["evidence_replayable_without_provider"] is False
    assert output["historical_complete_for_selected_categories"] is False
