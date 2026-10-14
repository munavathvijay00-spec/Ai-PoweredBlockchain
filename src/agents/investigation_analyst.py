"""Fail-closed LLM analyst for multi-agent investigation evidence.

Specialist agents collect facts. This analyst may summarize those facts, but it cannot
become a new source of blockchain claims. Invalid model output is rejected and callers
retain deterministic specialist synthesis.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from src.agents.evidence_contract import parse_json_object
from src.agents.explainer import get_explainer

_SENSITIVE = (
    "mixer", "tornado", "sanction", "ofac", "hack", "hacker", "scam", "phishing",
    "stolen", "launder", "criminal", "fraud", "malicious", "ransomware", "darknet",
)
_OVERCLAIMS = (
    "definitely", "certainly", "confirmed fraud", "confirmed illicit", "is fraudulent",
    "is a scam", "criminal activity", "money laundering", "malicious actor",
)


def _numbers(text: str) -> set[str]:
    no_hex = re.sub(r"0x[a-fA-F0-9]+", "", text or "")
    return {x.replace(",", "") for x in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", no_hex)}


def _prompt(ledger: List[Dict[str, Any]]) -> str:
    compact = [
        {"id": e.get("id"), "type": e.get("type"), "claim": e.get("claim"), "source": e.get("source")}
        for e in ledger[:30]
    ]
    return f"""You are the final analyst in an Ethereum investigation system.
You may ONLY use the evidence objects below. They are observations, not proof of wrongdoing.

EVIDENCE_LEDGER_JSON:
{json.dumps(compact, separators=(',', ':'), default=str)}

Return ONLY JSON:
{{
  "summary":"one concise investigation summary",
  "claims":[{{"text":"factual claim","evidence_ids":["agent:E1"]}}],
  "uncertainty":"one concise limitations sentence"
}}

Rules:
- Every factual claim needs one or more exact evidence IDs from the ledger.
- Never infer identity, ownership, intent, illegality, fraud, sanctions, theft, hacking,
  laundering, mixer use, or maliciousness unless cited evidence explicitly states it.
- Never introduce a number not present in the cited evidence.
- Use at most 5 claims.
- Do not state that review signals prove wrongdoing.
- Output no markdown and no text outside JSON.
"""


def _validate(payload: Dict[str, Any], ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    evidence = {str(e.get("id")): str(e.get("claim") or "") for e in ledger if e.get("id")}
    claims = payload.get("claims")
    reasons: List[str] = []
    if not isinstance(payload.get("summary"), str) or not isinstance(payload.get("uncertainty"), str):
        reasons.append("invalid_summary_or_uncertainty")
    if not isinstance(claims, list) or len(claims) > 5:
        reasons.append("invalid_claims_shape")
        claims = []

    for idx, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("text"), str):
            reasons.append(f"claim_{idx}_invalid_shape")
            continue
        refs = claim.get("evidence_ids")
        if not isinstance(refs, list) or not refs or any(str(ref) not in evidence for ref in refs):
            reasons.append(f"claim_{idx}_invalid_evidence_reference")
            continue
        text = claim["text"].strip()
        cited = " ".join(evidence[str(ref)] for ref in refs)
        lower = text.lower()
        cited_lower = cited.lower()
        if any(term in lower and term not in cited_lower for term in _SENSITIVE):
            reasons.append(f"claim_{idx}_unsupported_sensitive_term")
        if any(phrase in lower for phrase in _OVERCLAIMS):
            reasons.append(f"claim_{idx}_overclaim")
        if not _numbers(text).issubset(_numbers(cited)):
            reasons.append(f"claim_{idx}_invented_number")

    uncertainty = str(payload.get("uncertainty") or "").lower()
    if uncertainty and not any(term in uncertainty for term in ("not proof", "limited", "bounded", "uncertain", "coverage", "indicator")):
        reasons.append("uncertainty_missing_limitation")
    return {"grounded": not reasons, "reasons": reasons}


def _render(payload: Dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    claims = [str(c.get("text") or "").strip() for c in payload.get("claims") or [] if isinstance(c, dict)]
    uncertainty = str(payload.get("uncertainty") or "").strip()
    return " ".join([x for x in [summary, *claims, uncertainty] if x])


async def synthesize_agent_evidence(ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not ledger:
        return {"status": "abstained_no_evidence", "ai_used": False, "grounded": True}
    explainer = get_explainer()
    provider = str(getattr(explainer, "provider", "disabled") or "disabled").lower()
    model = getattr(explainer, "model", None)
    if not explainer._provider_configured():
        return {"status": "provider_not_configured", "provider": provider, "model": model, "ai_used": False, "grounded": True}

    started = time.monotonic()
    try:
        prompt = _prompt(ledger)
        async with explainer._semaphore:
            if provider == "ollama":
                raw = await explainer._call_ollama(prompt)
            elif provider == "groq":
                raw = await explainer._call_groq(prompt)
            else:
                return {"status": "provider_not_configured", "provider": provider, "model": model, "ai_used": False, "grounded": True}
    except Exception as exc:
        return {
            "status": "provider_no_output", "provider": provider, "model": model,
            "ai_used": False, "grounded": False, "error": type(exc).__name__,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    elapsed = int((time.monotonic() - started) * 1000)
    payload = parse_json_object(raw or "")
    if payload is None:
        return {"status": "structured_parse_rejected", "provider": provider, "model": model, "ai_used": False, "grounded": False, "latency_ms": elapsed}
    validation = _validate(payload, ledger)
    if not validation["grounded"]:
        return {"status": "grounding_rejected", "provider": provider, "model": model, "ai_used": False, "grounded": False, "validation": validation, "latency_ms": elapsed}
    rendered = _render(payload)
    if not rendered:
        return {"status": "grounding_rejected", "provider": provider, "model": model, "ai_used": False, "grounded": False, "validation": {"grounded": False, "reasons": ["empty_render"]}, "latency_ms": elapsed}
    return {
        "status": "grounded_ai", "provider": provider, "model": model,
        "ai_used": True, "grounded": True, "text": rendered,
        "structured_payload": payload, "validation": validation, "latency_ms": elapsed,
    }
