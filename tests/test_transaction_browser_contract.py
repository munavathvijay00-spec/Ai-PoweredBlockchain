"""Regression tests for existing transaction browsing behavior.

Run: python -m pytest tests/test_transaction_browser_contract.py -q
No live API calls, production writes, or seeded transactions.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.api import browse_routes as browse


@pytest.mark.parametrize("search,expected", [
    ("   ", None),
    ("0xABC", "%0xabc%"),
    ("a%b", r"%a\%b%"),
    ("a_b", r"%a\_b%"),
    (r"a\b", r"%a\\b%"),
])
def test_search_is_literal_and_blank_is_unfiltered(search, expected):
    where, args = browse._where(search, None, None, None, None)
    if expected is None:
        assert where == "TRUE"
        assert args == []
    else:
        assert args == [expected] * 3
        assert "ESCAPE" in where


def test_risk_and_eth_value_filter_parameters():
    where, args = browse._where(None, 20, 40, 0.25, 2)
    assert len(args) == 4
    assert args[0:2] == [20, 40]
    assert str(args[2]) == "250000000000000000.00"
    assert str(args[3]) == "2000000000000000000"
    assert "$1" in where and "$4" in where


class FakeDB:
    def __init__(self):
        self.entered = False
        self.exited = False
        self.isolation = None
        self.readonly = None

    @asynccontextmanager
    async def transaction(self, *, isolation=None, readonly=False):
        self.isolation = isolation
        self.readonly = readonly
        self.entered = True
        try:
            yield
        finally:
            self.exited = True


@pytest.mark.asyncio
async def test_browser_uses_one_read_only_snapshot_and_consistent_distribution():
    db = FakeDB()
    repo = type("Repo", (), {"db": db})()
    aggregate = dict(total=3, distinct_blocks=2, minimal=1, review=1,
                     high_review=1, critical=0, oldest_timestamp=None,
                     newest_timestamp=None, oldest_block=10, newest_block=11)
    rows = [dict(hash="0x" + "a" * 64, block_number=11, from_address="x",
                 to_address="y", risk_score=20)]
    async def aggregate_query(*_args):
        assert db.entered and not db.exited
        return aggregate

    async def cluster_query(*_args, **_kwargs):
        assert db.entered and not db.exited
        return rows, 1

    with patch.object(browse, "_aggregate_population", side_effect=aggregate_query), \\
         patch.object(browse, "_query_clusters", side_effect=cluster_query), \\
         patch.object(browse, "_load_entity_matches", new_callable=AsyncMock, return_value={}), \\
         patch.object(browse, "_decorate_row", side_effect=lambda row, *_: row):
        result = await browse.transaction_browser(limit=10, offset=0, search=None,
              min_risk=None, max_risk=None, min_value_eth=None, max_value_eth=None,
              sort="risk_desc", clustered=True, repo=repo)
    assert db.exited
    assert db.isolation == "repeatable_read"
    assert db.readonly is True
    assert result["matching_transactions"] == 3
    assert result["total"] == 1
    distribution = result["distribution"]
    assert sum(distribution[k] for k in ("minimal", "review", "high_review", "critical")) == distribution["population"]
    assert result["has_next"] is False


@pytest.mark.asyncio
async def test_export_reports_truncation_from_same_snapshot():
    db = FakeDB()
    repo = type("Repo", (), {"db": db})()
    rows = [dict(hash="0x" + "1" * 64, from_address="from", to_address="to",
                 value_wei="0", value_eth="0", block_number=1, timestamp="now",
                 risk_score=0, explanation_status="deterministic")]
    async def query(*_args, **_kwargs):
        assert db.entered and not db.exited
        return rows, {"total": 5001}
    with patch.object(browse, "_query_population", side_effect=query), \\
         patch.object(browse, "_load_entity_matches", new_callable=AsyncMock, return_value={}), \\
         patch.object(browse, "_decorate_row", side_effect=lambda row, *_: row):
        result = await browse.transaction_export(format="csv", search=None,
              min_risk=None, max_risk=None, min_value_eth=None,
              max_value_eth=None, sort="newest", repo=repo)
    assert db.exited and db.readonly
    assert result.headers["x-export-truncated"] == "true"
    assert result.headers["x-export-matching-transactions"] == "5001"
    assert result.headers["x-export-returned-transactions"] == "1"
