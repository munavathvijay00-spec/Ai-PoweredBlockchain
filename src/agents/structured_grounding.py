"""Structured, fail-closed AI reasoning over retained blockchain evidence.

The provider must return JSON claims. Claims are validated against the evidence contract
before rendering. Any parse, citation, semantic-support, numeric, or overclaim failure
returns the deterministic explanation instead.
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.agents.evidence_contract import (
    build_evidence_contract,
    contract_prompt_payload,
    parse_json_object,
    render_validated_payload,
    validate_claims_payload,
)
from src.agents.explainer import evidence_explanation, get_explainer


def _structured_prompt(contract: dict[str, Any]) -> str:
    payload = contract_prompt_payload(contract)
    return f"""You are a blockchain investigation assistant operating under a strict evidence contract.

EVIDENCE_CONTRACT_JSON:
{payload}

Return ONLY valid JSON with exactly this shape:
{{
  "summary": "one short non-technical sentence",
  "claims": [
    {{"text": "one factual claim", "evidence_ids": ["E1"]}}
  ],
  "uncertainty": "one short sentence explaining that indicators are not proof of wrongdoing"
}}

Hard rules:
- Every factual claim MUST cite one or more evidence_ids present in the contract.
- Do not create or infer wallet identity, ownership, intent, fraud, sanctions, scams, hacks,
  theft, laundering, exchange use, mixer use, historical behavior, or counterparties unless
  the cited evidence explicitly states it.
- Do not introduce a number unless it appears in the transaction object or cited evidence.
- Do not convert values to fiat or add market prices.
- Use at most 3 claims.
- If the evidence is insufficient for a factual claim, omit that claim.
- Never output markdown or prose outside the JSON object.
"""


async def structured_explain_with_audit(tx: dict[str, Any], factors: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = evidence_explanation(tx, factors)
    contract = build_evidence_contract(tx, factors)
    explainer = get_explainer()
    provider = str(getattr(explainer, "provider", "disabled") or "disabled").lower()
    model = getattr(explainer, "model", None)

    base = {
        "provider": provider,
        "model": model,
        "baseline": baseline,
        "explanation": baseline,
        "candidate": None,
        "structured_payload": None,
        "evidence_contract": contract,
        "ai_used": False,
        "grounded": True,
        "latency_ms": 0,
        "grounding_report": {
            "grounded": True,
            "checks": {},
            "reasons": ["deterministic_evidence_fallback"],
        },
    }

    if not factors or not contract.get("evidence"):
        return {**base, "status": "abstained_no_evidence"}
    if not explainer._provider_configured():
        return {**base, "status": "provider_not_configured"}

    started = time.monotonic()
    raw = None
    try:
        prompt = _structured_prompt(contract)
        async with explainer._semaphore:
            if provider == "ollama":
                raw = await explainer._call_ollama(prompt)
            elif provider == "groq":
                raw = await explainer._call_groq(prompt)
            else:
                return {**base, "status": "provider_not_configured"}
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        logger.warning(f"Structured AI explanation unavailable ({type(exc).__name__}); fail-closed fallback")
        return {
            **base,
            "status": "provider_no_output",
            "latency_ms": elapsed,
            "grounding_report": {
                "grounded": False,
                "checks": {"structured_json": False},
                "reasons": [f"provider_exception:{type(exc).__name__}"],
            },
        }

    elapsed = int((time.monotonic() - started) * 1000)
    parsed = parse_json_object(raw or "")
    if parsed is None:
        return {
            **base,
            "status": "structured_parse_rejected",
            "candidate": raw,
            "latency_ms": elapsed,
            "grounding_report": {
                "grounded": False,
                "checks": {"structured_json": False},
                "reasons": ["provider_output_not_valid_json_object"],
            },
        }

    validation = validate_claims_payload(parsed, contract)
    if not validation.get("grounded"):
        logger.warning("Rejected structured AI claims that failed evidence validation")
        return {
            **base,
            "status": "grounding_rejected",
            "candidate": raw,
            "structured_payload": parsed,
            "latency_ms": elapsed,
            "grounding_report": {
                **validation,
                "checks": {
                    "structured_json": True,
                    "claims_validated": False,
                },
            },
        }

    rendered = render_validated_payload(parsed)
    if not rendered.strip():
        return {
            **base,
            "status": "grounding_rejected",
            "candidate": raw,
            "structured_payload": parsed,
            "latency_ms": elapsed,
            "grounding_report": {
                **validation,
                "grounded": False,
                "checks": {"structured_json": True, "claims_validated": True, "rendered": False},
                "reasons": ["validated_payload_rendered_empty"],
            },
        }

    return {
        **base,
        "status": "grounded_ai",
        "candidate": raw,
        "structured_payload": parsed,
        "explanation": f"Grounded AI explanation: {rendered}",
        "ai_used": True,
        "grounded": True,
        "latency_ms": elapsed,
        "grounding_report": {
            **validation,
            "checks": {
                "structured_json": True,
                "claims_validated": True,
                "rendered": True,
            },
        },
    }
