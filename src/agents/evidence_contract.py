"""Structured evidence contract and strict validation for grounded AI outputs.

The LLM is a summarizer, never a source of blockchain facts. Every generated factual
statement must cite concrete retained evidence. Transaction facts are first-class evidence
items so a claim about an address, amount, block or risk score cannot hide behind an
unrelated detector citation.
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


def _append_evidence(evidence: list[dict[str, Any]], claim: str, source_type: str, source_ref: Any, **extra: Any) -> None:
    clean = str(claim or "").strip().rstrip(".")
    if not clean:
        return
    evidence.append({
        "evidence_id": f"E{len(evidence) + 1}",
        "claim": clean,
        "source_type": source_type,
        "source_ref": source_ref,
        **extra,
    })


def build_evidence_contract(tx: dict[str, Any], factors: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    tx_hash = tx.get("hash")
    tx_facts = {
        "tx_hash": tx_hash,
        "block_number": tx.get("block_number"),
        "from_address": tx.get("from_address"),
        "to_address": tx.get("to_address"),
        "value_wei": tx.get("value_wei", tx.get("value")),
        "risk_score": max(0, min(100, int(tx.get("risk_score") or 0))),
    }

    fact_templates = (
        ("tx_hash", "Transaction hash is {value}"),
        ("block_number", "Observed block number is {value}"),
        ("from_address", "Observed sender address is {value}"),
        ("to_address", "Observed recipient address is {value}"),
        ("value_wei", "Observed transaction value is {value} wei"),
        ("risk_score", "Deterministic risk score is {value} out of 100"),
    )
    for field, template in fact_templates:
        value = tx_facts.get(field)
        if value is not None and value != "":
            _append_evidence(
                evidence,
                template.format(value=value),
                "stored_transaction_fact",
                tx_hash,
                field=field,
            )

    for factor in factors or []:
        reason = str(factor.get("reason") or "").strip().rstrip(".")
        if not reason:
            continue
        extra: dict[str, Any] = {}
        if factor.get("points") is not None:
            try:
                extra["points"] = int(factor["points"])
            except (TypeError, ValueError, OverflowError):
                pass
        _append_evidence(
            evidence,
            reason,
            str(factor.get("source_type") or "stored_risk_factor"),
            factor.get("source_ref") or tx_hash,
            **extra,
        )

    return {
        "contract_version": "1.2",
        "transaction": tx_facts,
        "evidence": evidence,
        "policy": {
            "allow_uncited_factual_claims": False,
            "allow_uncited_summary": False,
            "allow_identity_or_intent_inference": False,
            "allow_new_numeric_claims": False,
            "require_uncertainty_language": True,
            "require_claim_evidence_semantic_support": True,
            "numeric_support_must_be_cited": True,
        },
    }


def contract_prompt_payload(contract: dict[str, Any]) -> str:
    return json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _extract_balanced_json_object(text: str) -> str | None:
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


def _validate_statement(
    text: Any,
    refs: Any,
    contract: dict[str, Any],
    allowed_ids: set[str],
    prefix: str,
    reasons: list[str],
) -> None:
    if not isinstance(text, str) or not text.strip():
        reasons.append(f"{prefix}_missing_text")
        return
    text = text.strip()
    if len(text) > 350:
        reasons.append(f"{prefix}_too_long")
    if not isinstance(refs, list) or not refs:
        reasons.append(f"{prefix}_uncited")
        return
    normalized = {str(ref).strip() for ref in refs}
    unknown = normalized.difference(allowed_ids)
    if unknown:
        reasons.append(f"{prefix}_unknown_evidence:" + ",".join(sorted(unknown)))
        return

    support = _support_text(contract, normalized)
    support_lower = support.lower()
    statement_lower = text.lower()
    unsupported_sensitive = [
        term for term in SENSITIVE_TERMS
        if term in statement_lower and term not in support_lower
    ]
    if unsupported_sensitive:
        reasons.append(f"{prefix}_unsupported_sensitive:" + ",".join(sorted(unsupported_sensitive)))

    # Numbers must exist in the evidence actually cited by this statement. Merely appearing
    # elsewhere in the transaction object is no longer sufficient.
    invented_numbers = _numbers(text).difference(_numbers(support))
    if invented_numbers:
        reasons.append(f"{prefix}_unsupported_numbers:" + ",".join(sorted(invented_numbers)))

    if any(phrase in statement_lower for phrase in (
        "definitely", "certainly", "confirmed fraud", "confirmed illicit",
        "is fraudulent", "is a scam", "proves wrongdoing",
    )):
        reasons.append(f"{prefix}_overclaim")


def validate_claims_payload(payload: Any, contract: dict[str, Any]) -> dict[str, Any]:
    """Validate structured LLM JSON before generated language is trusted.

    Expected shape:
      {"summary": {"text": str, "evidence_ids": ["E1"]},
       "claims": [{"text": str, "evidence_ids": ["E2"]}],
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
    if not isinstance(summary, dict):
        reasons.append("summary_not_cited_object")
    else:
        _validate_statement(
            summary.get("text"), summary.get("evidence_ids"), contract, allowed_ids, "summary", reasons
        )
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        reasons.append("missing_uncertainty")
    if not isinstance(claims, list):
        reasons.append("claims_not_array")
        claims = []
    if len(claims) > 5:
        reasons.append("too_many_claims")

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            reasons.append(f"claim_{index}_not_object")
            continue
        _validate_statement(
            claim.get("text"), claim.get("evidence_ids"), contract, allowed_ids, f"claim_{index}", reasons
        )

    if (claims or isinstance(summary, dict)) and not allowed_ids:
        reasons.append("claims_present_without_source_evidence")

    return {
        "grounded": not reasons,
        "reasons": reasons,
        "claim_count": len(claims),
        "allowed_evidence_ids": sorted(allowed_ids, key=lambda item: int(item[1:])),
    }


def render_validated_payload(payload: dict[str, Any]) -> str:
    """Render only already-validated structured statements into user-facing text."""
    summary = payload.get("summary") or {}
    summary_text = str(summary.get("text") or "").strip().rstrip(".") if isinstance(summary, dict) else ""
    summary_refs = [str(ref).strip() for ref in summary.get("evidence_ids") or []] if isinstance(summary, dict) else []
    rendered_summary = f"{summary_text} [{', '.join(summary_refs)}]." if summary_text and summary_refs else ""

    rendered_claims: list[str] = []
    for claim in payload.get("claims") or []:
        text = str(claim.get("text") or "").strip().rstrip(".")
        refs = [str(ref).strip() for ref in claim.get("evidence_ids") or []]
        if text and refs:
            rendered_claims.append(f"{text} [{', '.join(refs)}].")
    uncertainty = str(payload.get("uncertainty") or "").strip()
    return " ".join(part for part in [rendered_summary, " ".join(rendered_claims), uncertainty] if part)
