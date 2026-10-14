"""Truthful observed-data coverage, never presented as full Ethereum history."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.storage_budget import (
    LIVE_RETENTION_MINUTES,
    LINEAGE_RETENTION_BLOCKS,
    HISTORY_MAX_ROWS_PER_WALLET,
    HISTORY_MAX_ROWS_GLOBAL,
)

router = APIRouter(prefix="/api", tags=["data coverage"])
WALLET_PROVIDER_CATEGORIES = ["external", "erc20", "internal", "erc721", "erc1155"]


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

    try:
        persistent_history_rows = int(await repo.db.fetchval(
            "SELECT COUNT(*) FROM wallet_transfer_evidence"
        ) or 0)
    except Exception:
        persistent_history_rows = 0

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
        "automatic_shallow_reorg_recovery": True,
        "reorg_recovery_lineage_blocks": LINEAGE_RETENTION_BLOCKS,
        "historical_completeness": False,
        "note": "The worker verifies checkpoint hashes and parent continuity, keeps bounded canonical lineage, and automatically rewinds only when a common ancestor is verified. Deep or unverifiable forks still halt fail-closed.",
    }

    production_ready_for = [
        "recent native-transaction monitoring under a bounded free-tier retention budget",
        "bounded paginated wallet transfer investigation across ETH, internal value transfers, ERC-20, ERC-721 and ERC-1155",
        "persistent normalized evidence cache for investigated wallets",
        "evidence-linked transaction review",
    ]
    if entity_records:
        production_ready_for.append("source-attributed entity context for locally verified address matches")

    readiness = {
        "api_database": "connected",
        "ingestion": freshness_status,
        "checkpoint_integrity": checkpoint["status"],
        "recent_data_available": bool(stats["stored_transactions"]),
        "retention_window_minutes": LIVE_RETENTION_MINUTES,
        "historical_archive": False,
        "wallet_transfer_provider": "on_demand_paginated_with_bounded_cache",
        "wallet_transfer_categories": WALLET_PROVIDER_CATEGORIES,
        "internal_value_transfers": True,
        "nft_transfers": True,
        "entity_attribution": bool(entity_records),
        "entity_attribution_scope": "source_attributed_local_matches_only" if entity_records else "no_verified_records_loaded",
        "internal_trace_indexing": False,
        "detection_quality": "not_evaluated",
        "storage_profile": "free_tier_bounded",
        "production_ready_for": production_ready_for,
        "not_ready_for": [
            "complete chain-wide historical Ethereum warehousing",
            "complete EVM call-trace reconstruction",
            "comprehensive entity attribution across Ethereum",
            "sanctions/compliance verdicts without independent source review",
            "validated fraud-detection accuracy claims",
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
        "storage_budget": {
            "profile": "free_tier_bounded",
            "live_retention_minutes": LIVE_RETENTION_MINUTES,
            "canonical_lineage_rows_target": LINEAGE_RETENTION_BLOCKS,
            "historical_cache_rows_per_wallet": HISTORY_MAX_ROWS_PER_WALLET,
            "historical_cache_rows_global": HISTORY_MAX_ROWS_GLOBAL,
            "historical_cache_rows_current": persistent_history_rows,
            "raw_provider_payloads_persisted": False,
            "note": "Deep wallet history is provider-backed and re-fetchable; the local database stores only compact bounded evidence.",
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
            "note": f"The live native table retains about {LIVE_RETENTION_MINUTES} minutes. Older catch-up blocks preserve canonical checkpoint/lineage state without storing expired transaction rows.",
        },
        "wallet_transfer_provider": {
            "status": "on_demand_paginated_with_bounded_persistent_cache",
            "provider": "alchemy_getAssetTransfers",
            "categories": WALLET_PROVIDER_CATEGORIES,
            "sort": "newest_first",
            "historical_completeness": False,
            "page_size_shared_across_categories": True,
            "note": "Internal value transfers are provider-indexed transfer records, not complete EVM call traces. Cache eviction does not imply the provider lacks older history.",
        },
        "token_events": {
            "status": "on_demand_provider",
            "categories": ["erc20", "erc721", "erc1155"],
            "historical_completeness": False,
        },
        "internal_transfers": {
            "status": "on_demand_provider",
            "historical_completeness": False,
        },
        "internal_traces": {
            "status": "complete_call_traces_not_indexed",
            "historical_completeness": False,
        },
        "verified_entity_intelligence": {
            "status": "source_attributed_records_available" if entity_records else "no_records_loaded",
            "records": entity_records,
            "unique_addresses": entity_addresses,
            "sources": entity_sources,
            "newest_checked_at": entity_checked_at,
            "note": "This is a bounded local intelligence set. No local match is not evidence that no attribution exists elsewhere.",
        },
        "detection_quality": {
            "status": "not_evaluated",
            "precision": None,
            "recall": None,
            "false_positive_rate": None,
            "abstention_rate": None,
            "evaluation_harness": "available",
            "labeling_queue_tool": "scripts/build_labeling_queue.py",
            "evaluation_tool": "scripts/evaluate_detection.py",
            "protocol": "docs/DETECTION_EVALUATION.md",
            "note": "ChainScope does not claim validated fraud-detection accuracy until an independently labeled representative holdout set is evaluated.",
        },
        "reorg_verification": checkpoint,
        "wallet_history": {
            "status": "provider_backed_bounded_persistent_cache_plus_recent_native_index",
            "persistent_rows": persistent_history_rows,
            "historical_completeness": False,
        },
        "product_readiness": readiness,
        "limitations": [
            "The rolling native database is deliberately not a chain-wide Ethereum archive.",
            "No guarantee that all blocks between observed minimum and maximum have retained native transaction rows; canonical checkpoint continuity is tracked separately.",
            "An empty wallet result does not imply an inactive wallet.",
            "Provider-indexed internal value transfers are not a full EVM trace tree.",
            "Verified entity intelligence is only as broad and current as the source-attributed records loaded into the local table.",
            "Behavioral review signals have not yet been validated on an independently labeled representative holdout set.",
        ],
    }
