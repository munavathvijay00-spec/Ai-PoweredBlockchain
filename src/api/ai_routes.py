"""Non-secret status endpoints for the grounded AI subsystem."""
from fastapi import APIRouter, Depends

from src.agents.ai_audit import ai_quality_summary, provider_configuration
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/ai", tags=["grounded AI"])


@router.get("/status")
async def ai_status(repo: TransactionRepository = Depends(get_transaction_repo)):
    """Report configuration plus observed runtime proof without exposing credentials."""
    configuration = provider_configuration()
    quality = await ai_quality_summary(repo.db)
    runtime_verified = quality.get("last_grounded_at") is not None
    configured = bool(configuration.get("provider_configured"))

    if not configured:
        readiness_reason = configuration.get("configuration_reason")
    elif not runtime_verified:
        readiness_reason = "provider_configured_but_no_accepted_grounded_run_observed"
    else:
        readiness_reason = "accepted_grounded_run_observed"

    return {
        **configuration,
        "runtime_verified": runtime_verified,
        "real_grounded_ai_ready": configured and runtime_verified,
        "readiness_reason": readiness_reason,
        "quality": quality,
        "truthfulness_note": (
            "Runtime verification means ChainScope observed at least one model output that passed its grounding checks. "
            "It does not measure fraud-detection accuracy."
        ),
    }


@router.get("/quality")
async def ai_quality(repo: TransactionRepository = Depends(get_transaction_repo)):
    """Return aggregate grounding acceptance/fallback telemetry."""
    return await ai_quality_summary(repo.db)
