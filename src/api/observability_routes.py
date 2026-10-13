"""Factual operational health for ChainScope.

This endpoint reports measured service state only. It does not infer blockchain
coverage, fraud accuracy, or entity completeness from service availability.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.metrics import db_health_up, db_health_latency_seconds
from src.utils.config import get_settings

router = APIRouter(prefix="/api/observability", tags=["monitoring"])


async def _safe_table_count(repo: TransactionRepository, table: str):
    allowed = {"transactions", "addresses", "verified_address_intelligence"}
    if table not in allowed:
        raise ValueError("unsupported table")
    try:
        return int(await repo.db.fetchval(f"SELECT COUNT(*) FROM {table}"))
    except Exception:
        return None


@router.get("/health")
async def operational_health(repo: TransactionRepository = Depends(get_transaction_repo)):
    started = time.monotonic()
    db_ok = False
    db_error = None
    try:
        await repo.db.fetchval("SELECT 1")
        db_ok = True
        db_health_up.set(1)
    except Exception as exc:
        db_health_up.set(0)
        db_error = type(exc).__name__
    finally:
        db_health_latency_seconds.observe(time.monotonic() - started)

    checkpoint = None
    try:
        checkpoint = await repo.db.fetchrow(
            "SELECT last_block, block_hash, updated_at FROM ingest_cursor WHERE stream = 'ethereum_mainnet'"
        )
    except Exception:
        # Older deployments may use a different cursor stream or be mid-migration.
        try:
            checkpoint = await repo.db.fetchrow(
                "SELECT last_block, block_hash, updated_at FROM ingest_cursor ORDER BY updated_at DESC LIMIT 1"
            )
        except Exception:
            checkpoint = None

    settings = get_settings()
    provider = (settings.llm_provider or "disabled").lower()
    groq_ready = bool(settings.groq_api_key and settings.groq_api_key != "not-set")
    ollama_ready = provider == "ollama" and bool(settings.ollama_url)
    llm_ready = (provider == "groq" and groq_ready) or ollama_ready

    checkpoint_age_seconds = None
    if checkpoint and checkpoint.get("updated_at"):
        updated = checkpoint["updated_at"]
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        checkpoint_age_seconds = max(0, (datetime.now(timezone.utc) - updated).total_seconds())

    return {
        "service": "chainscope",
        "database": {
            "ok": db_ok,
            "error_type": db_error,
            "retained_transactions": await _safe_table_count(repo, "transactions") if db_ok else None,
            "tracked_addresses": await _safe_table_count(repo, "addresses") if db_ok else None,
            "verified_entity_rows": await _safe_table_count(repo, "verified_address_intelligence") if db_ok else None,
        },
        "ingestion": {
            "checkpoint_block": int(checkpoint["last_block"]) if checkpoint else None,
            "checkpoint_hash": checkpoint.get("block_hash") if checkpoint else None,
            "checkpoint_updated_at": checkpoint["updated_at"].isoformat() if checkpoint and checkpoint.get("updated_at") else None,
            "checkpoint_age_seconds": round(checkpoint_age_seconds, 2) if checkpoint_age_seconds is not None else None,
            "canonical_hash_guard": bool(checkpoint and checkpoint.get("block_hash")),
        },
        "ai": {
            "configured_provider": provider,
            "provider_ready": llm_ready,
            "grounding_required": True,
            "citations_required": True,
            "note": "AI is an optional wording layer over stored evidence; deterministic evidence remains the source of truth.",
        },
        "coverage": {
            "live_database_is_complete_history": False,
            "historical_wallet_provider_available": "alchemy.com" in settings.ethereum_rpc_url.lower(),
            "entity_attribution_is_complete": False,
        },
    }
