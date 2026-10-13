"""Risk evidence API response serialization."""
from datetime import datetime, timezone
from src.api.routes import _format_tx


def base_row(**overrides):
    row = {
        "hash": "0xabc", "from_address": "0xfrom", "to_address": "0xto",
        "value": 10**18, "block_number": 1,
        "timestamp": datetime.now(timezone.utc), "risk_score": 40,
        "risk_factors": '[{"reason":"Repeated transfer pattern","score":10}]',
        "ai_explanation": "Rule-based risk assessment: observed pattern",
    }
    row.update(overrides)
    return row


def test_decodes_jsonb_risk_evidence():
    response = _format_tx(base_row())
    assert response.risk_factors[0]["reason"] == "Repeated transfer pattern"
    assert response.value_eth == 1
    assert response.explanation_status == "deterministic"


def test_marks_grounded_ai_explanation_as_trusted_status():
    response = _format_tx(base_row(ai_explanation="Grounded AI explanation: review signal [E1]."))
    assert response.explanation_status == "grounded_ai"


def test_marks_unknown_legacy_explanation_unverified():
    response = _format_tx(base_row(ai_explanation="Old model says this is suspicious."))
    assert response.explanation_status == "legacy_unverified"


def test_invalid_risk_evidence_does_not_break_response():
    response = _format_tx(base_row(value=0, risk_score=0, risk_factors="not-json", ai_explanation=None))
    assert response.risk_factors == []
    assert response.explanation_status == "none"
