from src.agents.evidence_contract import (
    build_evidence_contract,
    parse_json_object,
    render_validated_payload,
    validate_claims_payload,
)


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


def _summary():
    return {"text": "The deterministic risk score is 62 out of 100", "evidence_ids": ["E6"]}


def test_contract_makes_transaction_facts_first_class_evidence():
    contract = _contract()
    assert [item["evidence_id"] for item in contract["evidence"]] == [
        "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"
    ]
    assert contract["evidence"][4]["field"] == "value_wei"
    assert contract["evidence"][5]["field"] == "risk_score"
    assert contract["transaction"]["risk_score"] == 62
    assert contract["contract_version"] == "1.2"


def test_summary_and_claims_require_real_evidence_ids():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "Rapid onward transfer observed", "evidence_ids": ["E7"]}],
            "uncertainty": "This signal does not prove wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is True


def test_uncited_summary_is_rejected():
    report = validate_claims_payload(
        {
            "summary": "Review recommended.",
            "claims": [],
            "uncertainty": "Uncertain.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert "summary_not_cited_object" in report["reasons"]


def test_unknown_evidence_id_is_rejected():
    report = validate_claims_payload(
        {
            "summary": _summary(),
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
            "summary": _summary(),
            "claims": [{"text": "Potentially suspicious", "evidence_ids": []}],
            "uncertainty": "Uncertain.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert "claim_0_uncited" in report["reasons"]


def test_sensitive_claim_cannot_hide_behind_unrelated_citation():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "This wallet used a mixer", "evidence_ids": ["E7"]}],
            "uncertainty": "This is not proof of wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert "claim_0_unsupported_sensitive:mixer" in report["reasons"]


def test_number_must_appear_in_the_cited_evidence_not_merely_transaction_record():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "The risk score is 62", "evidence_ids": ["E7"]}],
            "uncertainty": "This is not proof of wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert any("unsupported_numbers:62" in reason for reason in report["reasons"])


def test_number_is_allowed_when_specific_transaction_fact_is_cited():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "The deterministic risk score is 62 out of 100", "evidence_ids": ["E6"]}],
            "uncertainty": "This is not proof of wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is True


def test_new_numeric_claim_is_rejected():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "There were 999 linked transfers", "evidence_ids": ["E7"]}],
            "uncertainty": "This is not proof of wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert any("unsupported_numbers:999" in reason for reason in report["reasons"])


def test_explicit_overclaim_is_rejected_even_with_valid_citation():
    report = validate_claims_payload(
        {
            "summary": _summary(),
            "claims": [{"text": "This is definitely suspicious", "evidence_ids": ["E7"]}],
            "uncertainty": "This is not proof of wrongdoing.",
        },
        _contract(),
    )
    assert report["grounded"] is False
    assert "claim_0_overclaim" in report["reasons"]


def test_fenced_json_is_parsed_and_rendered_after_validation():
    raw = '''```json
{"summary":{"text":"The deterministic risk score is 62 out of 100","evidence_ids":["E6"]},"claims":[{"text":"Rapid onward transfer observed","evidence_ids":["E7"]}],"uncertainty":"This signal is not proof of wrongdoing."}
```'''
    payload = parse_json_object(raw)
    assert payload is not None
    report = validate_claims_payload(payload, _contract())
    assert report["grounded"] is True
    rendered = render_validated_payload(payload)
    assert "[E6]" in rendered
    assert "[E7]" in rendered
    assert "not proof of wrongdoing" in rendered
