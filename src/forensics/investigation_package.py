"""Build deterministic, hash-addressed ChainScope investigation packages."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_package(
    *,
    case: dict[str, Any],
    coverage: dict[str, Any],
    evidence: list[dict[str, Any]],
    forensics: dict[str, Any],
    entity_intelligence: dict[str, Any] | None = None,
    wallet_behavior_features: dict[str, Any] | None = None,
    transaction_anomaly: dict[str, Any] | None = None,
    supervised_ml: dict[str, Any] | None = None,
    ai_investigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sections = {
        "case": case,
        "coverage": coverage,
        "evidence": evidence,
        "forensics": forensics,
        "entity_intelligence": entity_intelligence or {},
        "wallet_behavior_features": wallet_behavior_features or {},
        "transaction_anomaly": transaction_anomaly or {},
        "supervised_ml": supervised_ml or {},
        "ai_investigation": ai_investigation or {},
    }
    hashes = {name: sha256_json(payload) for name, payload in sections.items()}
    manifest_basis = {
        "schema_version": 1,
        "chain_id": 1,
        "case_id": case.get("case_id"),
        "address": case.get("address"),
        "section_sha256": hashes,
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chain_id": 1,
        "case_id": case.get("case_id"),
        "address": case.get("address"),
        "sections": sections,
        "manifest": {
            **manifest_basis,
            "package_sha256": sha256_json(manifest_basis),
            "reproducibility_note": "Section hashes are deterministic over canonical JSON. generated_at is excluded from package_sha256.",
        },
        "interpretation_policy": {
            "external_attribution_is_not_generated_by_chainscope": True,
            "forensic_findings_are_observations_not_verdicts": True,
            "wallet_behavior_features_are_descriptive_not_labels": True,
            "transaction_anomaly_is_not_criminality_probability": True,
            "supervised_ml_is_not_promoted_without_quality_gate": True,
            "ai_claims_must_be_grounded_in_deterministic_findings": True,
            "coverage_limits_must_remain_visible": True,
        },
    }
