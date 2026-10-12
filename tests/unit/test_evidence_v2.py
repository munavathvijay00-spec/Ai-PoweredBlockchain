from src.risk.evidence_v2 import assess_evidence


def test_large_transfer_not_high_risk_by_itself():
    result = assess_evidence([{"factor": "whale_transaction", "reason": "2000 ETH"}], "0xabc")
    assert result["assessment"] == "insufficient_evidence"
    assert result["probability"] is None
    assert result["calibrated"] is False
    assert result["observed_facts"][0]["source_tx_hash"] == "0xabc"


def test_behavior_requires_review_not_conviction():
    result = assess_evidence([{"factor": "same_block_fan_out", "reason": "many recipients"}], "0xdef")
    assert result["assessment"] == "review"
    assert result["confidence"] == "limited"
    assert result["behavioral_indicators"][0]["source_tx_hash"] == "0xdef"


def test_missing_data_is_not_low_risk():
    result = assess_evidence([])
    assert result["assessment"] == "insufficient_evidence"
    assert result["confidence"] == "unknown"


def test_unrecognized_factor_not_treated_as_verified():
    result = assess_evidence([{"factor": "unknown_intelligence"}])
    assert result["assessment"] == "insufficient_evidence"
    assert len(result["unverified_indicators"]) == 1
