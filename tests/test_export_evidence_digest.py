"""Regression checks for deterministic export evidence fingerprints."""
from src.api.browse_routes import _evidence_digest


def test_digest_repeatable_and_key_order_independent():
    a = {"hash": "0xabc", "risk_score": 20, "value_wei": "1", "block_number": 1,
         "risk_factors": [{"factor": "observed", "points": 20}]}
    b = dict(reversed(list(a.items())))
    assert _evidence_digest([a]) == _evidence_digest([b])
    assert len(_evidence_digest([a])) == 64


def test_digest_changes_when_evidence_changes():
    a = {"hash": "0xabc", "risk_score": 20, "value_wei": "1"}
    b = {**a, "risk_score": 21}
    assert _evidence_digest([a]) != _evidence_digest([b])


def test_digest_detects_missing_and_reordered_records():
    a = {"hash": "0xabc"}
    b = {"hash": "0xdef"}
    assert _evidence_digest([a, b]) != _evidence_digest([b, a])
    assert _evidence_digest([a, b]) != _evidence_digest([a])
