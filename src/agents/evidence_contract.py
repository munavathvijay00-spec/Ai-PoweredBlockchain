"""Structured evidence contract and strict validation for grounded AI outputs.

The LLM is a summarizer, never a source of blockchain facts. Every factual claim must
cite stored evidence, and sensitive/numeric claims are checked against the cited
material before generated prose can reach an investigator.
"""
from __future__ import annotations

import json
import re
from typing import Any

EVIDENCE_ID_RE = re.compile(r"^E\d+$")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
SENSITIVE_TERMS = (
    "mixer", "tornado", "sanction", "ofac", "hack", "hacker", "scam", "phishing",
    "stolen", "launder", "criminal", "fraud", "malicious", "exchange", "bridge",
    "darknet", "ransomware",
)


def _numbers(text: str) -> set[str]:
    without_hex = re.sub(r"0x[a-fA-F0-9]+", "", text or "")
    return {value.replace(",", "") for value in NUMBER_RE.findall(without_hex)}


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
        "contract_version": "1.1",
        "transaction": tx_facts,
        "evidence": evidence,
        "policy": {
            "allow_uncited_factual_claims": False,
            "allow_identity_or_intent_inference": False,
            "allow_new_numeric_claims": False,
            "require_uncertainty_language": True,
            "require_claim_evidence_semantic_support": True,
        },
    }


def contract_prompt_payload(contract: dict[str, Any]) -> str:
    return json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _extract_balanced_json_object(text: str) -> str | None:
    """Return the first balanced JSON object outside quoted-string braces."""
    start = -1
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start:index + 1]
    return None


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse one provider JSON object without trusting surrounding model prose.

    Providers sometimes wrap valid JSON in markdown fences or a short preamble even when
    explicitly instructed not to. ChainScope may extract that object, but the extracted
    payload still has to pass the normal evidence-grounding validator before any AI text
    is accepted.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    candidates = [text]
    extracted = _extract_balanced_json_object(text)
    if extracted and extracted != text:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _support_text(contract: dict[str, Any], refs: set[str]) -> str:
    parts: list[str] = []
    for item in contract.get("evidence") or []:
        if str(item.get("evidence_id")) in refs:
            parts.append(str(item.get("claim") or ""))
            if item.get("points") is not None:
                parts.append(str(item.get("points")))
    return " ".join(parts)


def _transaction_support_text(contract: dict[str, Any]) -> str:
    tx = contract.get("transaction") or {}
    return " ".join(str(value) for value in tx.values() if value is not None)


def validate_claims_payload(payload: Any, contract: dict[str, Any]) -> dict[str, Any]:
    """Validate structured LLM JSON before generated language is trusted.

    Expected shape:
      {"summary": str,
       "claims": [{"text": str, "evidence_ids": ["E1"]}],
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
    if len(claims) > 5:
        reasons.append("too_many_claims")

    tx_support = _transaction_support_text(contract)
    global_numeric_support = _numbers(tx_support)

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            reasons.append(f"claim_{index}_not_object")
            continue
        text = claim.get("text")
        refs = claim.get("evidence_ids")
        if not isinstance(text, str) or not text.strip():
            reasons.append(f"claim_{index}_missing_text")
            continue
        text = text.strip()
        if len(text) > 350:
            reasons.append(f"claim_{index}_too_long")

        if not isinstance(refs, list) or not refs:
            reasons.append(f"claim_{index}_uncited")
            continue
        normalized = {str(ref).strip() for ref in refs}
        unknown = normalized.difference(allowed_ids)
        if unknown:
            reasons.append(f"claim_{index}_unknown_evidence:" + ",".join(sorted(unknown)))
            continue

        support = _support_text(contract, normalized)
        support_lower = support.lower()
        claim_lower = text.lower()

        unsupported_sensitive = [
            term for term in SENSITIVE_TERMS
            if term in claim_lower and term not in support_lower
        ]
        if unsupported_sensitive:
            reasons.append(
                f"claim_{index}_unsupported_sensitive:" + ",".join(sorted(unsupported_sensitive))
            )

        allowed_numbers = _numbers(support).union(global_numeric_support)
        invented_numbers = _numbers(text).difference(allowed_numbers)
        if invented_numbers:
            reasons.append(
                f"claim_{index}_unsupported_numbers:" + ",".join(sorted(invented_numbers))
            )

        if any(phrase in claim_lower for phrase in (
            "definitely", "certainly", "confirmed fraud", "confirmed illicit",
            "is fraudulent", "is a scam", "proves wrongdoing",
        )):
            reasons.append(f"claim_{index}_overclaim")

    if claims and not allowed_ids:
        reasons.append("claims_present_without_source_evidence")

    return {
        "grounded": not reasons,
        "reasons": reasons,
        "claim_count": len(claims),
        "allowed_evidence_ids": sorted(allowed_ids),
    }


def render_validated_payload(payload: dict[str, Any]) -> str:
    """Render only already-validated structured claims into user-facing text."""
    summary = str(payload.get("summary") or "").strip()
    claims = payload.get("claims") or []
    rendered_claims: list[str] = []
    for claim in claims:
        text = str(claim.get("text") or "").strip().rstrip(".")
        refs = [str(ref).strip() for ref in claim.get("evidence_ids") or []]
        if text and refs:
            rendered_claims.append(f"{text} [{', '.join(refs)}].")
    uncertainty = str(payload.get("uncertainty") or "").strip()
    parts = [part for part in [summary, " ".join(rendered_claims), uncertainty] if part]
    return " ".join(parts)
