from src.agents.wallet_investigator import (
    build_wallet_evidence,
    deterministic_wallet_report,
    validate_wallet_payload,
)


ROOT = "0x" + "1" * 40
TX = "0x" + "a" * 64


def contract():
    analysis = {
        "root": ROOT,
        "record_count": 4,
        "incoming_records": 1,
        "outgoing_records": 3,
        "unique_counterparties": 3,
        "findings": [
            {
                "code": "fan_out",
                "title": "Observed fan-out from investigated wallet",
                "explanation": "The investigated wallet sent the same canonical asset to at least three distinct observed recipients.",
                "details": {"unique_recipients": 3, "asset_key": "eip155:1/native:ETH"},
                "evidence": [{"tx_hash": TX}],
            }
        ],
        "limitations": ["No finding proves wrongdoing."],
    }
    return build_wallet_evidence(analysis)


def test_accepts_supported_cited_claim():
    evidence = contract()
    payload = {
        "summary": {
            "text": "The wallet shows fan-out to 3 observed recipients.",
            "finding_ids": ["F1"],
        },
        "claims": [],
        "uncertainty": "This observation does not establish intent or wrongdoing.",
    }
    result = validate_wallet_payload(payload, evidence)
    assert result["grounded"] is True


def test_rejects_invented_number():
    evidence = contract()
    payload = {
        "summary": {
            "text": "The wallet shows fan-out to 99 observed recipients.",
            "finding_ids": ["F1"],
        },
        "claims": [],
        "uncertainty": "This is not proof of wrongdoing.",
    }
    result = validate_wallet_payload(payload, evidence)
    assert result["grounded"] is False
    assert any("unsupported_numbers" in reason for reason in result["reasons"])


def test_rejects_unsupported_sensitive_claim():
    evidence = contract()
    payload = {
        "summary": {
            "text": "This wallet is involved in fraud.",
            "finding_ids": ["F1"],
        },
        "claims": [],
        "uncertainty": "Review manually.",
    }
    result = validate_wallet_payload(payload, evidence)
    assert result["grounded"] is False
    assert any("unsupported_sensitive" in reason for reason in result["reasons"])


def test_deterministic_report_preserves_finding_reference():
    text = deterministic_wallet_report(contract())
    assert "[F1]" in text
    assert "not proof of wrongdoing" in text
