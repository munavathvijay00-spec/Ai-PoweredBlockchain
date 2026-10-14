"""Audit trail and readiness reporting for grounded AI explanations.

The product must be able to prove when a real model was called, whether its output
passed grounding validation, and when deterministic evidence was used instead.
No secret values are ever returned by these helpers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from src.utils.config import get_settings


_PLACEHOLDER_KEYS = {"", "not-set", "none", "null", "changeme", "placeholder"}


def _configured_secret(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.lower() not in _PLACEHOLDER_KEYS


def provider_configuration() -> Dict[str, Any]:
    settings = get_settings()
    provider = str(settings.llm_provider or "disabled").strip().lower()
    if provider == "groq":
        model = str(settings.groq_model or "").strip() or None
        configured = _configured_secret(settings.groq_api_key) and bool(model)
        reason = "configured" if configured else "missing_groq_api_key_or_model"
    elif provider == "ollama":
        model = str(settings.llm_model or "").strip() or None
        configured = bool(str(settings.ollama_url or "").strip()) and bool(model)
        reason = "configured_unverified" if configured else "missing_ollama_configuration"
    else:
        model = None
        configured = False
        reason = "unsupported_or_disabled_provider"

    return {
        "provider": provider,
        "model": model,
        "provider_configured": configured,
        "configuration_reason": reason,
    }


async def ensure_ai_audit_schema(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_explanation_runs (
            id BIGSERIAL PRIMARY KEY,
            tx_hash VARCHAR(66) NOT NULL,
            provider TEXT NOT NULL,
            model TEXT,
            status TEXT NOT NULL,
            ai_used BOOLEAN NOT NULL DEFAULT FALSE,
            grounded BOOLEAN NOT NULL DEFAULT FALSE,
            baseline_sha256 CHAR(64) NOT NULL,
            candidate_text TEXT,
            final_explanation TEXT NOT NULL,
            grounding_report JSONB NOT NULL DEFAULT '{}'::jsonb,
            latency_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_explanation_runs_tx_created
        ON ai_explanation_runs(tx_hash, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_explanation_runs_status_created
        ON ai_explanation_runs(status, created_at DESC)
        """
    )


async def record_ai_run(db, *, tx_hash: str, baseline: str, audit: Dict[str, Any]) -> None:
    await ensure_ai_audit_schema(db)
    baseline_hash = hashlib.sha256((baseline or "").encode("utf-8")).hexdigest()
    report = audit.get("grounding_report") or {}
    await db.execute(
        """
        INSERT INTO ai_explanation_runs (
            tx_hash, provider, model, status, ai_used, grounded,
            baseline_sha256, candidate_text, final_explanation,
            grounding_report, latency_ms
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11)
        """,
        tx_hash.lower(),
        str(audit.get("provider") or "disabled"),
        audit.get("model"),
        str(audit.get("status") or "unknown"),
        bool(audit.get("ai_used")),
        bool(audit.get("grounded")),
        baseline_hash,
        audit.get("candidate"),
        str(audit.get("explanation") or baseline),
        json.dumps(report),
        int(audit["latency_ms"]) if audit.get("latency_ms") is not None else None,
    )


async def ai_quality_summary(
    db,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    await ensure_ai_audit_schema(db)
    where = ""
    args = []
    if provider is not None and model is not None:
        where = "WHERE provider=$1 AND model=$2"
        args = [str(provider), str(model)]
    elif provider is not None:
        where = "WHERE provider=$1"
        args = [str(provider)]

    row = await db.fetchrow(
        f"""
        SELECT
            COUNT(*) AS total_runs,
            COUNT(*) FILTER (WHERE ai_used AND grounded) AS grounded_ai_runs,
            COUNT(*) FILTER (WHERE status IN ('grounding_rejected','structured_parse_rejected')) AS grounding_rejections,
            COUNT(*) FILTER (WHERE status = 'structured_parse_rejected') AS structured_parse_rejections,
            COUNT(*) FILTER (WHERE status = 'provider_no_output') AS provider_no_output,
            COUNT(*) FILTER (WHERE status = 'provider_not_configured') AS provider_not_configured,
            COUNT(*) FILTER (WHERE status = 'abstained_no_evidence') AS abstained_no_evidence,
            MAX(created_at) FILTER (WHERE ai_used AND grounded) AS last_grounded_at,
            MAX(created_at) AS last_attempt_at
        FROM ai_explanation_runs
        {where}
        """,
        *args,
    )
    total = int(row["total_runs"] or 0)
    grounded = int(row["grounded_ai_runs"] or 0)
    rejected = int(row["grounding_rejections"] or 0)
    failed = int(row["provider_no_output"] or 0)
    attempted_model_runs = grounded + rejected + failed
    return {
        "provider_filter": provider,
        "model_filter": model,
        "total_runs": total,
        "grounded_ai_runs": grounded,
        "grounding_rejections": rejected,
        "structured_parse_rejections": int(row["structured_parse_rejections"] or 0),
        "provider_no_output": failed,
        "provider_not_configured": int(row["provider_not_configured"] or 0),
        "abstained_no_evidence": int(row["abstained_no_evidence"] or 0),
        "model_attempts": attempted_model_runs,
        "grounding_acceptance_rate": (grounded / attempted_model_runs) if attempted_model_runs else None,
        "last_grounded_at": row["last_grounded_at"],
        "last_attempt_at": row["last_attempt_at"],
        "metric_scope": "LLM grounding acceptance only; not transaction-detection accuracy",
    }
