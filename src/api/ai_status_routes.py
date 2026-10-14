"""Truthful AI provider readiness and grounded-generation status.

This endpoint never returns credentials. It reports whether a configured provider can
actually be called by the backend and separates model availability from the number of
stored explanations that passed the grounding contract.
"""
from fastapi import APIRouter, Depends

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.utils.config import get_settings

router = APIRouter(prefix="/api/ai", tags=["ai readiness"])


def provider_readiness(settings) -> dict:
    provider = str(settings.llm_provider or "disabled").strip().lower()
    model = str(settings.llm_model or "").strip() or None

    if provider == "groq":
        key = str(settings.groq_api_key or "").strip()
        ready = bool(key and key != "not-set")
        reason = "ready" if ready else "missing_groq_api_key"
    elif provider == "ollama":
        url = str(settings.ollama_url or "").strip()
        ready = bool(url)
        reason = "configured_endpoint_not_health_checked" if ready else "missing_ollama_url"
    else:
        ready = False
        reason = "provider_disabled_or_unsupported"

    return {
        "provider": provider,
        "model": model,
        "configured": ready,
        "reason": reason,
    }


@router.get("/status")
async def ai_status(repo: TransactionRepository = Depends(get_transaction_repo)):
    settings = get_settings()
    provider = provider_readiness(settings)
    row = await repo.db.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE ai_explanation LIKE 'Grounded AI explanation:%') AS grounded_ai,
            COUNT(*) FILTER (WHERE ai_explanation LIKE 'Evidence-based transaction review:%'
                              OR ai_explanation LIKE 'Rule-based risk assessment:%'
                              OR ai_explanation LIKE 'Evidence-based assessment:%') AS deterministic,
            COUNT(*) FILTER (WHERE risk_score >= 20) AS review_transactions
        FROM transactions
        """
    )
    grounded = int(row["grounded_ai"] or 0)
    deterministic = int(row["deterministic"] or 0)
    review_transactions = int(row["review_transactions"] or 0)

    return {
        **provider,
        "grounded_ai_explanations": grounded,
        "deterministic_explanations": deterministic,
        "review_transactions": review_transactions,
        "ai_share_of_review_transactions": round(grounded / review_transactions, 4) if review_transactions else 0.0,
        "grounding_contract": "stored transaction facts + stored risk factors + valid [E#] references",
        "claims_policy": "AI may rewrite evidence; it may not invent identity, intent, fraud, sanctions, amounts, or unsupported behavior.",
        "production_ready": bool(provider["configured"]),
    }
