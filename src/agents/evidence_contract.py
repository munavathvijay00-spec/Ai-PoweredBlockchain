"""Structured evidence contract for grounded AI outputs.

LLMs may summarize evidence, but every factual claim must cite an evidence_id that
exists in the supplied contract.  The model is never allowed to create new facts.
"""
from __future__ import annotations

import json
import re
from typing import Any


EVIDENCE_ID_RE = re.compile(r"^E\d+$")


def build_evidence_contract(tx: dict[str, Any], factors: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    tx_facts = {
        "tx_hash": tx.get("hash"),
        "block_number": tx.get("block_number"),
        "from_address": tx.get("from_address"),
        "to_address": tx.get("to_address"),
        "value_wei": tx.get("value_wei", tx.get("value")),
        "risk_score": max(0, min(100, int(tx.get("risk_score") or 0))),
    }
    for index, factor in enumerate(factors or [], start=1):
        reason = str(factor.get("reason") or "").strip().rstrip(".")
        if not reason:
            continue
        item = {
            "evidence_id": f"E{index}",
            "claim": reason,
            "source_type": str(factor.get("source_type") or "stored_risk_factor"),
            "source_ref": factor.get("source_ref") or tx.get("hash"),
        }
        if factor.get("points") is not None:
            try:
                item["points"] = int(factor["points"])
            except (TypeError, ValueError, OverflowError):
                pass
        evidence.append(item)
    return {
        "contract_version": "1.0",
        "transaction": tx_facts,
        "evidence": evidence,
        "policy": {
            "allow_uncited_factual_claims": False,
            "allow_identity_or_intent_inference": False,
            "allow_new_numeric_claims": False,
            "require_uncertainty_language": True,
        },
    }


def contract_prompt_payload(contract: dict[str, Any]) -> str:
    """Canonical JSON inserted into prompts so the same facts can be audited/replayed."""
    return json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate_claims_payload(payload: Any, contract: dict[str, Any]) -> dict[str, Any]:
    """Validate structured LLM JSON before any generated prose is trusted.

    Expected shape:
      {"summary": str, "claims": [{"text": str, "evidence_ids": ["E1"]}],
       "uncertainty": str}
    """
    reasons: list[str] = []
    allowed_ids = {
        str(item.get("evidence_id"))
        for item in contract.get("evidence") or []
        if EVIDENCE_ID_RE.match(str(item.get("evidence_id") or ""))
    }
    if not isinstance(payload, dict):
        return {"grounded": False, "reasons": ["payload_not_object"], "claim_count": 0}

    summary = payload.get("summary")
    claims = payload.get("claims")
    uncertainty = payload.get("uncertainty")
    if not isinstance(summary, str) or not summary.strip():
        reasons.append("missing_summary")
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        reasons.append("missing_uncertainty")
    if not isinstance(claims, list):
        reasons.append("claims_not_array")
        claims = []

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            reasons.append(f"claim_{index}_not_object")
            continue
        text = claim.get("text")
        refs = claim.get("evidence_ids")
        if not isinstance(text, str) or not text.strip():
            reasons.append(f"claim_{index}_missing_text")
        if not isinstance(refs, list) or not refs:
            reasons.append(f"claim_{index}_uncited")
            continue
        normalized = {str(ref).strip() for ref in refs}
        unknown = normalized.difference(allowed_ids)
        if unknown:
            reasons.append(f"claim_{index}_unknown_evidence:" + ",".join(sorted(unknown)))

    if claims and not allowed_ids:
        reasons.append("claims_present_without_source_evidence")

    return {
        "grounded": not reasons,
        "reasons": reasons,
        "claim_count": len(claims),
        "allowed_evidence_ids": sorted(allowed_ids),
    }
