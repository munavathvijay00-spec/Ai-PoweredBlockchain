from src.risk.behavior import analyze_block_behavior, apply_behavior_risk


def tx(i, sender="0xa", recipient=None):
    return {"hash": str(i), "from_address": sender,
            "to_address": recipient or f"0x{i:040x}", "block_number": 42}


def test_fan_out_requires_many_distinct_recipients():
    factors = analyze_block_behavior([tx(i) for i in range(12)])
    assert all(any(f["factor"] == "same_block_fan_out" for f in fs) for fs in factors.values())


def test_repeated_transfers_have_evidence():
    factors = analyze_block_behavior([tx(i, recipient="0xb") for i in range(6)])
    assert factors["0"][0]["observed_transfer_count"] == 6
    assert factors["0"][0]["block_number"] == 42


def test_small_normal_block_has_no_behavior_alerts():
    assert analyze_block_behavior([tx(1), tx(2)]) == {}


def test_blacklist_risk_is_unchanged():
    result = apply_behavior_risk({"score": 100, "factors": []}, tx(1), {"1": [{"points": 15}]})
    assert result == {"score": 100, "factors": []}


def test_behavior_score_adds_only_observed_points():
    factors = analyze_block_behavior([tx(i) for i in range(12)])
    result = apply_behavior_risk({"score": 10, "factors": []}, tx(0), factors)
    assert result["score"] == 25
