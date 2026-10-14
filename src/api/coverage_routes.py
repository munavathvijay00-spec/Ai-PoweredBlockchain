"""Truthful observed-data coverage, never presented as full Ethereum history."""
import json
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


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


@router.get("/coverage")
async def get_coverage(repo: TransactionRepository = Depends(get_transaction_repo)):
    stats = await repo.db.fetchrow("""
        SELECT MIN(block_number) AS min_block, MAX(block_number) AS max_block,
               MIN(timestamp) AS oldest_observed_at, MAX(timestamp) AS newest_observed_at,
               COUNT(*) AS stored_transactions,
               COUNT(DISTINCT block_number) AS blocks_with_stored_transactions,
               COUNT(*) FILTER (
                   WHERE ai_explanation LIKE 'Grounded AI explanation:%'
               ) AS ai_generated_explanations,
               COUNT(*) FILTER (
                   WHERE ai_explanation LIKE 'Rule-based risk assessment:%'
                      OR ai_explanation LIKE 'Evidence-based assessment:%'
                      OR ai_explanation LIKE 'Evidence-based transaction review:%'
               ) AS deterministic_explanations
        FROM transactions
    """)
    try:
        cursor = await repo.db.fetchrow("""
            SELECT last_block, block_hash, updated_at
            FROM ingest_cursor WHERE stream = 'ethereum_mainnet'
        """)
    except Exception:
        cursor = None

    entity_stats = None
    entity_store = "none"
    try:
        entity_stats = await repo.db.fetchrow("""
            SELECT COUNT(*) AS records,
                   COUNT(DISTINCT source) AS sources,
                   COUNT(DISTINCT address) AS addresses,
                   MAX(verified_at) AS newest_checked_at
            FROM entity_attributions
            WHERE chain_id=1 AND (expires_at IS NULL OR expires_at > NOW())
        """)
        entity_store = "entity_attributions"
    except Exception:
        try:
            entity_stats = await repo.db.fetchrow("""
                SELECT COUNT(*) AS records,
                       COUNT(DISTINCT source) AS sources,
                       COUNT(DISTINCT address) AS addresses,
                       MAX(checked_at) AS newest_checked_at
                FROM verified_address_intelligence
            """)
            entity_store = "verified_address_intelligence"
        except Exception:
            entity_stats = None

    try:
        persistent_history_rows = int(await repo.db.fetchval(
            "SELECT COUNT(*) FROM wallet_transfer_evidence"
        ) or 0)
    except Exception:
        persistent_history_rows = 0

    try:
        label_rows = int(await repo.db.fetchval(
            "SELECT COUNT(*) FROM detection_labels"
        ) or 0)
        unique_labelled_transactions = int(await repo.db.fetchval(
            "SELECT COUNT(DISTINCT tx_hash) FROM detection_labels"
        ) or 0)
    except Exception:
        label_rows = 0
        unique_labelled_transactions = 0

    try:
        latest_evaluation = await repo.db.fetchrow("""
            SELECT id,evaluator_version,threshold,sample_size,metrics,label_sources,created_at
            FROM detection_evaluations
            ORDER BY created_at DESC
            LIMIT 1
        """)
    except Exception:
        latest_evaluation = None

    entity_records = int(entity_stats["records"] or 0) if entity_stats else 0
    entity_sources = int(entity_stats["sources"] or 0) if entity_stats else 0
    entity_addresses = int(entity_stats["addresses"] or 0) if entity_stats else 0
    entity_checked_at = entity_stats["newest_checked_at"] if entity_stats else None
    ai_generated_explanations = int((stats.get("ai_generated_explanations") if hasattr(stats, "get") else 0) or 0)
    deterministic_explanations = int((stats.get("deterministic_explanations") if hasattr(stats, "get") else 0) or 0)

    evaluation_metrics = _json_object(latest_evaluation.get("metrics")) if latest_evaluation else {}
    evaluation_measured = bool(latest_evaluation)

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
        "detection_quality": "independently_evaluated" if evaluation_measured else "not_evaluated",
        "ai_explanation_mode": "grounded_llm_rewrites_present" if ai_generated_explanations else "deterministic_evidence_only_in_retained_window",
        "storage_profile": "free_tier_bounded",
        "production_ready_for": production_ready_for,
        "not_ready_for": [
            "complete chain-wide historical Ethereum warehousing",
            "complete EVM call-trace reconstruction",
            "comprehensive entity attribution across Ethereum",
            "sanctions/compliance verdicts without independent source review",
            "fraud-probability claims beyond independently labelled validation evidence",
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
            "store": entity_store,
            "note": "This is a bounded local intelligence set. No local match is not evidence that no attribution exists elsewhere.",
        },
        "explanation_quality": {
            "grounded_ai_rows": ai_generated_explanations,
            "deterministic_evidence_rows": deterministic_explanations,
            "status": "grounded_ai_present" if ai_generated_explanations else "deterministic_only",
            "note": "Only explanations stored with the Grounded AI prefix passed the LLM grounding validator. Deterministic evidence explanations are not counted as AI-generated.",
        },
        "detection_quality": {
            "status": "independently_evaluated" if evaluation_measured else "not_evaluated",
            "precision": evaluation_metrics.get("precision") if evaluation_measured else None,
            "recall": evaluation_metrics.get("recall") if evaluation_measured else None,
            "false_positive_rate": evaluation_metrics.get("false_positive_rate") if evaluation_measured else None,
            "abstention_rate": evaluation_metrics.get("abstention_rate") if evaluation_measured else None,
            "decision_coverage": evaluation_metrics.get("decision_coverage") if evaluation_measured else None,
            "sample_size": int(latest_evaluation["sample_size"]) if latest_evaluation else 0,
            "evaluation_id": latest_evaluation["id"] if latest_evaluation else None,
            "evaluator_version": latest_evaluation["evaluator_version"] if latest_evaluation else None,
            "threshold": latest_evaluation["threshold"] if latest_evaluation else None,
            "created_at": latest_evaluation["created_at"] if latest_evaluation else None,
            "label_sources": latest_evaluation.get("label_sources") if latest_evaluation else [],
            "label_rows": label_rows,
            "unique_labelled_transactions": unique_labelled_transactions,
            "evaluation_harness": "available",
            "labeling_queue_tool": "scripts/build_labeling_queue.py",
            "evaluation_tool": "scripts/evaluate_detection.py",
            "protocol": "docs/DETECTION_EVALUATION.md",
            "note": (
                "Metrics describe only the independent labelled validation set and are not calibrated fraud probabilities."
                if evaluation_measured
                else "ChainScope does not claim validated fraud-detection accuracy until an independently labeled representative holdout set is evaluated."
            ),
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
            "Detection metrics, when present, apply only to the independently labelled evaluation set and do not establish a universal fraud probability.",
        ],
    }
