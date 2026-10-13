from datetime import datetime

from src.agents.explainer import evidence_explanation
from src.api.routes import _format_tx


def _row(*, tx_hash: str, value_wei: int, block_number: int, stored_explanation: str | None = None):
    return {
        "hash": tx_hash,
        "from_address": "0x1111111111111111111111111111111111111111",
        "to_address": "0x2222222222222222222222222222222222222222",
        "value": value_wei,
        "block_number": block_number,
        "timestamp": datetime(2026, 10, 13, 17, 0, 0),
        "risk_score": 40,
        "risk_factors": [
            {
                "factor": "whale_transaction",
                "points": 40,
                "reason": "Whale-sized transfer",
            }
        ],
        "ai_explanation": stored_explanation,
    }


def test_same_score_transactions_get_transaction_specific_explanations():
    first = evidence_explanation(
        _row(
            tx_hash="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            value_wei=2383999500000000000000,
            block_number=26185054,
        ),
        [{"factor": "whale_transaction", "points": 40, "reason": "Whale-sized transfer"}],
    )
    second = evidence_explanation(
        _row(
            tx_hash="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            value_wei=1318000000000000000000,
            block_number=26185044,
        ),
        [{"factor": "whale_transaction", "points": 40, "reason": "Whale-sized transfer"}],
    )

    assert first != second
    assert "2,383.9995 ETH" in first
    assert "block 26,185,054" in first
    assert "1,318 ETH" in second
    assert "block 26,185,044" in second
    assert "[E1]" in first
    assert "+40 points" in first


def test_api_replaces_legacy_generic_text_with_live_deterministic_context():
    result = _format_tx(
        _row(
            tx_hash="0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            value_wei=1821079100000000000000,
            block_number=26185027,
            stored_explanation="High value transaction detected. Review recommended.",
        )
    )

    assert result.explanation_status == "deterministic"
    assert result.ai_explanation.startswith("Evidence-based transaction review:")
    assert "High value transaction detected" not in result.ai_explanation
    assert "1,821.0791 ETH" in result.ai_explanation
    assert "block 26,185,027" in result.ai_explanation


def test_api_preserves_current_grounded_ai_explanation():
    grounded = (
        "Grounded AI explanation: This transaction scored 40/100 because [E1] "
        "a whale-sized transfer was recorded. This is a review indicator, not proof of wrongdoing."
    )
    result = _format_tx(
        _row(
            tx_hash="0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
            value_wei=2000000000000000000000,
            block_number=26185030,
            stored_explanation=grounded,
        )
    )

    assert result.explanation_status == "grounded_ai"
    assert result.ai_explanation == grounded
