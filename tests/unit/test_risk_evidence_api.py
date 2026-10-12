"""Risk evidence API response serialization."""
from datetime import datetime, timezone
from src.api.routes import _format_tx


def test_decodes_jsonb_risk_evidence():
    row = {
        "hash": "0xabc", "from_address": "0xfrom", "to_address": "0xto",
        "value": 10**18, "block_number": 1,
        "timestamp": datetime.now(timezone.utc), "risk_score": 40,
        "risk_factors": '[{"reason":"Repeated transfer pattern","score":10}]',
        "ai_explanation": "Rule-based risk assessment: observed pattern",
    }
    response = _format_tx(row)
    assert response.risk_factors[0]["reason"] == "Repeated transfer pattern"
    assert response.value_eth == 1


def test_invalid_risk_evidence_does_not_break_response():
    row = {
        "hash": "0xabc", "from_address": "0xfrom", "to_address": "0xto",
        "value": 0, "block_number": 1,
        "timestamp": datetime.now(timezone.utc), "risk_score": 0,
        "risk_factors": "not-json",
    }
    assert _format_tx(row).risk_factors == []
