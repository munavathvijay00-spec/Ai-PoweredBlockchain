"""Truthful observed-data coverage, never presented as full Ethereum history."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api", tags=["data coverage"])


def _age_seconds(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - value).total_seconds()))


def _freshness(age_seconds):
    if age_seconds is None:
        return "unknown"
    if age_seconds <= 60:
        return "live"
    if age_seconds <= 180:
        return "delayed"
    return "stale"


@router.get("/coverage")
async def get_coverage(repo: TransactionRepository = Depends(get_transaction_repo)):
    stats = await repo.db.fetchrow("""
        SELECT MIN(block_number) AS min_block, MAX(block_number) AS max_block,
               MIN(timestamp) AS oldest_observed_at, MAX(timestamp) AS newest_observed_at,
               COUNT(*) AS stored_transactions,
               COUNT(DISTINCT block_number) AS blocks_with_stored_transactions
        FROM transactions
    """)
    try:
        cursor = await repo.db.fetchrow("""
            SELECT last_block, block_hash, updated_at
            FROM ingest_cursor WHERE stream = 'ethereum_mainnet'
        """)
    except Exception:
        cursor = None

    try:
        entity_stats = await repo.db.fetchrow("""
            SELECT COUNT(*) AS records,
                   COUNT(DISTINCT source) AS sources,
                   COUNT(DISTINCT address) AS addresses,
                   MAX(checked_at) AS newest_checked_at
            FROM verified_address_intelligence
        """)
    except Exception:
        entity_stats = None

    entity_records = int(entity_stats["records"] or 0) if entity_stats else 0
    entity_sources = int(entity_stats["sources"] or 0) if entity_stats else 0
    entity_addresses = int(entity_stats["addresses"] or 0) if entity_stats else 0
    entity_checked_at = entity_stats["newest_checked_at"] if entity_stats else None

    cursor_age = _age_seconds(cursor["updated_at"] if cursor else None)
    newest_tx_age = _age_seconds(stats["newest_observed_at"])
    freshness_status = _freshness(cursor_age)

    checkpoint = {
        "status": "checkpoint_hash_recorded" if cursor and cursor["block_hash"] else "not_verified",
        "checkpoint_block": cursor["last_block"] if cursor else None,
        "checkpoint_hash": cursor["block_hash"] if cursor else None,
        "updated_at": cursor["updated_at"] if cursor else None,
        "age_seconds": cursor_age,
        "freshness_status": freshness_status,
        "automatic_rollback": False,
        "historical_completeness": False,
        "note": "The ingestion worker checks canonical checkpoint hashes and parent continuity. This does not verify older records, recover orphaned transactions, or prove full chain coverage.",
    }

    production_ready_for = [
        "recent native-transaction monitoring",
        "bounded wallet transfer investigation",
        "evidence-linked transaction review",
    ]
    if entity_records:
        production_ready_for.append("source-attributed entity context for locally verified address matches")

    readiness = {
        "api_database": "connected",
        "ingestion": freshness_status,
        "checkpoint_integrity": checkpoint["status"],
        "recent_data_available": bool(stats["stored_transactions"]),
        "retention_window_minutes": 30,
        "historical_archive": False,
        "wallet_transfer_provider": "on_demand",
        "entity_attribution": bool(entity_records),
        "entity_attribution_scope": "source_attributed_local_matches_only" if entity_records else "no_verified_records_loaded",
        "internal_trace_indexing": False,
        "production_ready_for": production_ready_for,
        "not_ready_for": [
            "complete historical wallet reconstruction",
            "comprehensive entity attribution across Ethereum",
            "sanctions/compliance verdicts without independent source review",
            "multi-hop forensic tracing guarantees",
        ],
    }

    return {
        "chain_id": 1,
        "network": "ethereum-mainnet",
        "ingestion_health": {
            "status": freshness_status,
            "checkpoint_block": cursor["last_block"] if cursor else None,
            "checkpoint_updated_at": cursor["updated_at"] if cursor else None,
            "checkpoint_age_seconds": cursor_age,
            "newest_observed_transaction_age_seconds": newest_tx_age,
            "stored_transactions": stats["stored_transactions"],
        },
        "native_transactions": {
            "status": "partial_recent_retained",
            "stored_transactions": stats["stored_transactions"],
            "min_observed_block": stats["min_block"],
            "max_observed_block": stats["max_block"],
            "blocks_with_stored_transactions": stats["blocks_with_stored_transactions"],
            "oldest_observed_at": stats["oldest_observed_at"],
            "newest_observed_at": stats["newest_observed_at"],
            "historical_completeness": False,
            "note": "Worker starts at chain tip on first run and currently deletes transactions older than 30 minutes. Observed block bounds do not prove contiguous coverage.",
        },
        "token_events": {"status": "on_demand_only", "historical_completeness": False},
        "internal_traces": {"status": "not_indexed", "historical_completeness": False},
        "verified_entity_intelligence": {
            "status": "source_attributed_records_available" if entity_records else "no_records_loaded",
            "records": entity_records,
            "unique_addresses": entity_addresses,
            "sources": entity_sources,
            "newest_checked_at": entity_checked_at,
            "note": "This is a bounded local intelligence set. No local match is not evidence that no attribution exists elsewhere.",
        },
        "reorg_verification": checkpoint,
        "wallet_history": {"status": "sampled_from_retained_native_transactions", "historical_completeness": False},
        "product_readiness": readiness,
        "limitations": [
            "No complete address-indexed Ethereum history is available from this database.",
            "No guarantee that all blocks between observed minimum and maximum were indexed.",
            "An empty wallet result does not imply an inactive wallet.",
            "Verified entity intelligence is only as broad and current as the source-attributed records loaded into the local table.",
        ],
    }
