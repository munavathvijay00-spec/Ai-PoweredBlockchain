from src.agents.evidence_contract import build_evidence_contract, validate_claims_payload


def _contract():
    return build_evidence_contract(
        {
            "hash": "0xabc",
            "block_number": 123,
            "from_address": "0xfrom",
            "to_address": "0xto",
            "value_wei": 10,
            "risk_score": 62,
        },
        [
            {"reason": "Rapid onward transfer observed", "points": 20, "source_ref": "0xabc"},
            {"reason": "Counterparty matched a verified intelligence signal", "points": 30},
        ],
    )


def test_contract_assigns_stable_evidence_ids():
    contract = _contract()
    assert [item["evidence_id"] for item in contract["evidence"]] == ["E1", "E2"]
    assert contract["transaction"]["risk_score"] == 62


def test_claims_require_real_evidence_ids():
    report = validate_claims_payload(
        {
            "summary": "Review recommended.",
            "claims": [{"text": "Rapid onward transfer observed", "evidence_ids": ["E1"]}],
            "uncertainty": "This signal does not prove wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is True


def test_unknown_evidence_id_is_rejected():
    report = validate_claims_payload(
        {
            "summary": "Review recommended.",
            "claims": [{"text": "This wallet is a scam", "evidence_ids": ["E99"]}],
            "uncertainty": "Uncertain.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert any("unknown_evidence" in reason for reason in report["reasons"])


def test_uncited_claim_is_rejected():
    report = validate_claims_payload(
        {
            "summary": "Review recommended.",
            "claims": [{"text": "Potentially suspicious", "evidence_ids": []}],
            "uncertainty": "Uncertain.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert "claim_0_uncited" in report["reasons"]
