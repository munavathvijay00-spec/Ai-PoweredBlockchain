from datetime import datetime, timezone, timedelta
import pytest

from src.risk.scorer import RiskScorer


@pytest.mark.asyncio
async def test_bidirectional_history_adds_specific_evidence():
    scorer = RiskScorer(bursty_threshold=100)
    now = datetime.now(timezone.utc)
    counterparty = "0x" + "b" * 40
    history = [
        {"direction": "outgoing", "counterparty": counterparty, "to_address": counterparty, "value": 1, "timestamp": now - timedelta(minutes=6)},
        {"direction": "incoming", "counterparty": counterparty, "to_address": "0x" + "a" * 40, "value": 1, "timestamp": now - timedelta(minutes=5)},
        {"direction": "outgoing", "counterparty": counterparty, "to_address": counterparty, "value": 1, "timestamp": now - timedelta(minutes=4)},
        {"direction": "incoming", "counterparty": counterparty, "to_address": "0x" + "a" * 40, "value": 1, "timestamp": now - timedelta(minutes=3)},
    ]
    result = await scorer.score_transaction(
        {"value": 0, "from_address": "0x" + "a" * 40, "to_address": counterparty},
        history,
    )
    factors = {factor["factor"]: factor for factor in result["factors"]}
    assert "ping_pong_pattern" in factors
    assert factors["ping_pong_pattern"]["counterparty"] == counterparty
    assert factors["ping_pong_pattern"]["incoming_count"] == 2
    assert factors["ping_pong_pattern"]["outgoing_count"] == 2


@pytest.mark.asyncio
async def test_missing_history_does_not_invent_behavior():
    scorer = RiskScorer()
    result = await scorer.score_transaction(
        {"value": 0, "from_address": "0x" + "a" * 40, "to_address": "0x" + "b" * 40},
        [],
    )
    names = {factor["factor"] for factor in result["factors"]}
    assert "bursty_activity" not in names
    assert "ping_pong_pattern" not in names
    assert "repeated_counterparty" not in names
