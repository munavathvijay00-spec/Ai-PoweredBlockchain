"""External threshold sensitivity never changes production scorer settings."""
import pytest
from src.risk.external_benchmark import external_threshold_sensitivity, SOURCE_NAME


class FakeDB:
    async def execute(self, *args):
        return "CREATE TABLE"
    async def fetch(self, query, source):
        assert source == SOURCE_NAME
        return [
            {"source_row_idx": 1, "tx_hash": "0x" + "a"*64, "label": 1, "value_wei_text": "100000000000000000000", "gas": 21000, "gas_price_text": "1", "block_number": 1},
            {"source_row_idx": 2, "tx_hash": "0x" + "b"*64, "label": 0, "value_wei_text": "0", "gas": 21000, "gas_price_text": "1", "block_number": 2},
        ]


class FakeScorer:
    async def score_transaction(self, tx, history, **kwargs):
        assert history == []
        if int(tx["value"]) > 0:
            return {"score": 30, "factors": [{"factor": "large_transaction", "points": 30}]}
        return {"score": 0, "factors": []}


@pytest.mark.asyncio
async def test_external_thresholds_show_abstention_without_behavioral_evidence():
    report = await external_threshold_sensitivity(FakeDB(), FakeScorer())
    assert report["sample_size"] == 2
    assert report["representative"] is False
    assert report["live_thresholds_modified"] is False
    assert all(row["abstentions"] == 2 for row in report["thresholds"])
    assert all(row["precision"] is None for row in report["thresholds"])
