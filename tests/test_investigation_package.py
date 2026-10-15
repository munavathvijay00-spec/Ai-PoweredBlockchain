from src.forensics.investigation_package import build_package, sha256_json


def sample_package():
    return build_package(
        case={
            "case_id": "case-1",
            "address": "0x1111111111111111111111111111111111111111",
            "external_attribution": {
                "publisher": "External Authority",
                "attribution": "Example attribution",
            },
        },
        coverage={"selected_category_history_complete": True},
        evidence=[{"tx_hash": "0x" + "a" * 64, "value_text": "1"}],
        forensics={"findings": [{"code": "fan_out", "not_a_fraud_verdict": True}]},
        entity_intelligence={"status": "no_local_match"},
        wallet_behavior_features={"features": {"unique_counterparties": 3}},
        transaction_anomaly={"available": False},
        supervised_ml={"production_quality_gate_passed": False},
        ai_investigation={"status": "deterministic_fallback", "grounded": True},
    )


def test_package_hash_is_stable_across_generation_time():
    first = sample_package()
    second = sample_package()
    assert first["manifest"]["package_sha256"] == second["manifest"]["package_sha256"]
    assert first["manifest"]["section_sha256"] == second["manifest"]["section_sha256"]


def test_section_hash_detects_evidence_change():
    package = sample_package()
    original = package["manifest"]["section_sha256"]["evidence"]
    modified = list(package["sections"]["evidence"])
    modified.append({"tx_hash": "0x" + "b" * 64, "value_text": "2"})
    assert sha256_json(modified) != original


def test_interpretation_policy_keeps_external_attribution_separate():
    package = sample_package()
    policy = package["interpretation_policy"]
    assert policy["external_attribution_is_not_generated_by_chainscope"] is True
    assert policy["forensic_findings_are_observations_not_verdicts"] is True
    assert policy["transaction_anomaly_is_not_criminality_probability"] is True
    assert policy["ai_claims_must_be_grounded_in_deterministic_findings"] is True


def test_section_hashes_match_payloads():
    package = sample_package()
    for name, payload in package["sections"].items():
        assert package["manifest"]["section_sha256"][name] == sha256_json(payload)
