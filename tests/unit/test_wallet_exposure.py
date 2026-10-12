from src.risk.wallet_exposure import find_direct_exposures, apply_exposure_risk


SANCTIONED = "0x" + "a" * 40
OTHER = "0x" + "b" * 40
THIRD = "0x" + "c" * 40


def test_direct_exposure_requires_observed_transfer():
    txs = [{"from_address": SANCTIONED, "to_address": OTHER, "hash": "0x123"}]
    exposures = find_direct_exposures(txs, {SANCTIONED: {}})
    assert exposures[OTHER] == (SANCTIONED, "0x123", "received_from_sanctioned")
    assert THIRD not in exposures


def test_exposure_is_not_a_sanctions_designation():
    evidence = {OTHER: {"sanctioned_address": SANCTIONED, "evidence_tx_hash": "0x123",
                        "direction": "received_from_sanctioned"}}
    result = apply_exposure_risk(
        {"score": 10, "factors": []},
        {"from_address": OTHER, "to_address": THIRD},
        evidence, {SANCTIONED: {}},
    )
    assert result["score"] == 35
    assert result["factors"][0]["factor"] == "direct_sanctions_counterparty_exposure"


def test_direct_sanctions_score_stays_critical():
    result = apply_exposure_risk(
        {"score": 100, "factors": []},
        {"from_address": SANCTIONED, "to_address": OTHER},
        {OTHER: {}}, {SANCTIONED: {}},
    )
    assert result["score"] == 100
    assert not result["factors"]
