"""Non-secret status endpoints for the grounded AI subsystem."""
from fastapi import APIRouter, Depends

from src.agents.ai_audit import ai_quality_summary, provider_configuration
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/ai", tags=["grounded AI"])


@router.get("/status")
async def ai_status(repo: TransactionRepository = Depends(get_transaction_repo)):
    """Report configuration plus runtime proof for the exact active provider/model."""
    configuration = provider_configuration()
    quality = await ai_quality_summary(
        repo.db,
        provider=configuration.get("provider"),
        model=configuration.get("model"),
    )
    runtime_verified = quality.get("last_grounded_at") is not None
    configured = bool(configuration.get("provider_configured"))

    if not configured:
        readiness_reason = configuration.get("configuration_reason")
    elif not runtime_verified:
        readiness_reason = "provider_model_configured_but_no_accepted_grounded_run_observed"
    else:
        readiness_reason = "accepted_grounded_run_observed_for_active_provider_model"

    return {
        **configuration,
        "runtime_verified": runtime_verified,
        "real_grounded_ai_ready": configured and runtime_verified,
        "readiness_reason": readiness_reason,
        "quality": quality,
        "truthfulness_note": (
            "Runtime verification means the currently configured provider/model produced at least one output "
            "that passed ChainScope grounding checks. It does not measure fraud-detection accuracy."
        ),
    }


@router.get("/quality")
async def ai_quality(repo: TransactionRepository = Depends(get_transaction_repo)):
    """Return grounding telemetry for the currently configured provider/model."""
    configuration = provider_configuration()
    return await ai_quality_summary(
        repo.db,
        provider=configuration.get("provider"),
        model=configuration.get("model"),
    )
