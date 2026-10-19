"""Regression: a zero native-ETH amount alone is not suspicious."""
import pytest
from src.risk.scorer import RiskScorer

@pytest.mark.asyncio
async def test_zero_value_has_context_but_no_automatic_risk_points():
    scorer = RiskScorer()
    result = await scorer.score_transaction({"value": "0"}, address_history=[])
    assert result["score"] == 0
    assert any(f["factor"] == "zero_value" and f["points"] == 0 for f in result["factors"])

@pytest.mark.asyncio
async def test_zero_value_does_not_suppress_independent_blocklist_evidence():
    scorer = RiskScorer()
    result = await scorer.score_transaction({"value": "0"}, address_history=[], is_blacklisted=True)
    assert result["score"] == 100
    assert result["factors"][0]["factor"] == "blacklisted_address"
