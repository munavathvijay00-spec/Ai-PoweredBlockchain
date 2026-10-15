"""Fail-closed wallet-level AI reasoning over forensic findings.

The model may organize and explain findings, but it cannot create blockchain facts. Every
factual statement must cite one or more finding IDs produced by deterministic forensic
analysis. Invalid model output is discarded in favor of the deterministic report.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from src.agents.explainer import get_explainer

NUMBER_RE = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
SENSITIVE_TERMS = (
    "fraud", "fraudulent", "scam", "phishing", "sanction", "ofac", "mixer",
    "launder", "criminal", "stolen", "hack", "hacker", "malicious", "taint",
)


def _numbers(text: str) -> set[str]:
    without_hex = re.sub(r"0x[a-fA-F0-9]+", "", text or "")
    return {item.replace(",", "") for item in NUMBER_RE.findall(without_hex)}


def build_wallet_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for index, finding in enumerate(analysis.get("findings") or [], start=1):
        evidence = finding.get("evidence") or []
        findings.append({
            "finding_id": f"F{index}",
            "code": finding.get("code"),
            "title": finding.get("title"),
            "explanation": finding.get("explanation"),
            "details": finding.get("details") or {},
            "transaction_hashes": [item.get("tx_hash") for item in evidence if item.get("tx_hash")][:20],
        })
    return {
        "contract_version": "wallet-investigation-1.0",
        "root": analysis.get("root"),
        "record_count": analysis.get("record_count", 0),
        "incoming_records": analysis.get("incoming_records", 0),
        "outgoing_records": analysis.get("outgoing_records", 0),
        "unique_counterparties": analysis.get("unique_counterparties", 0),
        "findings": findings,
        "limitations": analysis.get("limitations") or [],
    }


def deterministic_wallet_report(contract: dict[str, Any]) -> str:
    findings = contract.get("findings") or []
    if not findings:
        return (
            f"Observed {contract.get('record_count', 0)} cached transfer records for the investigated wallet. "
            "No supported forensic pattern was identified in the currently loaded evidence; absence of a finding is not evidence of benign activity."
        )
    parts = []
    for finding in findings[:4]:
        parts.append(f"[{finding['finding_id']}] {finding.get('title')}: {finding.get('explanation')}")
    return " ".join(parts) + " These observations are review cues, not proof of wrongdoing or ownership."


def _support_text(contract: dict[str, Any], refs: set[str]) -> str:
    chunks = []
    for item in contract.get("findings") or []:
        if item.get("finding_id") in refs:
            chunks.append(json.dumps(item, sort_keys=True, default=str))
    return " ".join(chunks)


def validate_wallet_payload(payload: Any, contract: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    allowed = {item.get("finding_id") for item in contract.get("findings") or []}
    allowed.discard(None)
    if not isinstance(payload, dict):
        return {"grounded": False, "reasons": ["payload_not_object"]}

    statements = []
    summary = payload.get("summary")
    if isinstance(summary, dict):
        statements.append(("summary", summary))
    else:
        reasons.append("summary_not_object")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        reasons.append("claims_not_array")
        claims = []
    if len(claims) > 5:
        reasons.append("too_many_claims")
    for index, claim in enumerate(claims):
        statements.append((f"claim_{index}", claim))

    for prefix, statement in statements:
        if not isinstance(statement, dict):
            reasons.append(f"{prefix}_not_object")
            continue
        text = statement.get("text")
        refs = statement.get("finding_ids")
        if not isinstance(text, str) or not text.strip():
            reasons.append(f"{prefix}_missing_text")
            continue
        if not isinstance(refs, list) or not refs:
            reasons.append(f"{prefix}_uncited")
            continue
        normalized = {str(ref) for ref in refs}
        unknown = normalized - allowed
        if unknown:
            reasons.append(f"{prefix}_unknown_refs:" + ",".join(sorted(unknown)))
            continue
        support = _support_text(contract, normalized)
        unsupported_numbers = _numbers(text) - _numbers(support)
        if unsupported_numbers:
            reasons.append(f"{prefix}_unsupported_numbers:" + ",".join(sorted(unsupported_numbers)))
        lower = text.lower()
        support_lower = support.lower()
        sensitive = [term for term in SENSITIVE_TERMS if term in lower and term not in support_lower]
        if sensitive:
            reasons.append(f"{prefix}_unsupported_sensitive:" + ",".join(sorted(sensitive)))
        if any(phrase in lower for phrase in ("definitely", "confirmed fraud", "proves", "is criminal")):
            reasons.append(f"{prefix}_overclaim")

    uncertainty = payload.get("uncertainty")
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        reasons.append("missing_uncertainty")
    return {"grounded": not reasons, "reasons": reasons, "claim_count": len(claims)}


def _prompt(contract: dict[str, Any]) -> str:
    return f"""You are ChainScope's evidence-grounded wallet investigation assistant.

FORENSIC_FINDINGS_JSON:
{json.dumps(contract, sort_keys=True, separators=(',', ':'), default=str)}

Return ONLY JSON:
{{
  "summary": {{"text": "short finding-backed summary", "finding_ids": ["F1"]}},
  "claims": [{{"text": "one factual observation", "finding_ids": ["F1"]}}],
  "uncertainty": "short limitation statement"
}}

Rules:
- Every factual statement must cite finding_ids from FORENSIC_FINDINGS_JSON.
- Use only facts explicitly contained in the cited findings.
- Never infer identity, ownership, intent, taint, fraud, criminality, sanctions, laundering, or final destination.
- Never introduce a number not present in the cited finding.
- Do not treat absence of a finding as proof of safety.
- Use at most 5 claims.
- If findings are weak, keep the answer narrow.
- Return no markdown and no text outside the JSON object.
"""


def _render(payload: dict[str, Any]) -> str:
    parts = []
    summary = payload.get("summary") or {}
    if isinstance(summary, dict) and summary.get("text"):
        refs = ", ".join(summary.get("finding_ids") or [])
        parts.append(f"{summary['text']} [{refs}].")
    for claim in payload.get("claims") or []:
        if isinstance(claim, dict) and claim.get("text"):
            refs = ", ".join(claim.get("finding_ids") or [])
            parts.append(f"{claim['text']} [{refs}].")
    if payload.get("uncertainty"):
        parts.append(str(payload["uncertainty"]).strip())
    return " ".join(parts)


async def investigate_wallet(analysis: dict[str, Any]) -> dict[str, Any]:
    contract = build_wallet_evidence(analysis)
    baseline = deterministic_wallet_report(contract)
    explainer = get_explainer()
    provider = str(getattr(explainer, "provider", "disabled") or "disabled").lower()
    model = getattr(explainer, "model", None)
    base = {
        "provider": provider,
        "model": model,
        "ai_used": False,
        "grounded": True,
        "explanation": baseline,
        "evidence_contract": contract,
        "status": "deterministic",
        "latency_ms": 0,
    }
    if not contract.get("findings"):
        return {**base, "status": "abstained_no_supported_findings"}
    if not explainer._provider_configured():
        return {**base, "status": "provider_not_configured"}

    started = time.monotonic()
    try:
        async with explainer._semaphore:
            if provider == "ollama":
                raw = await explainer._call_ollama(_prompt(contract))
            elif provider == "groq":
                raw = await explainer._call_groq(_prompt(contract), json_mode=True)
            else:
                return {**base, "status": "provider_not_configured"}
    except Exception as exc:
        return {
            **base,
            "status": "provider_no_output",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "grounding_report": {"grounded": False, "reasons": [f"provider_exception:{type(exc).__name__}"]},
        }

    elapsed = int((time.monotonic() - started) * 1000)
    try:
        parsed = json.loads(str(raw).strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            **base, "status": "structured_parse_rejected", "latency_ms": elapsed,
            "grounding_report": {"grounded": False, "reasons": ["invalid_json"]},
        }
    validation = validate_wallet_payload(parsed, contract)
    if not validation.get("grounded"):
        return {
            **base, "status": "grounding_rejected", "latency_ms": elapsed,
            "grounding_report": validation,
        }
    rendered = _render(parsed).strip()
    if not rendered:
        return {**base, "status": "grounding_rejected", "latency_ms": elapsed}
    return {
        **base,
        "status": "grounded_ai",
        "ai_used": True,
        "explanation": rendered,
        "structured_payload": parsed,
        "grounding_report": validation,
        "latency_ms": elapsed,
    }
