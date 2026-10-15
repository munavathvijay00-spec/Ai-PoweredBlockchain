"""Unified truth surface for ChainScope investigation readiness.

This endpoint intentionally distinguishes selected-provider pagination completeness from
full Ethereum/EVM completeness and blocks users from interpreting weak evaluation or ML
state as production-grade intelligence.
"""
from __future__ import annotations

import json
import re
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.ml.model_registry import model_status
from src.risk.external_benchmark import external_benchmark_summary

router = APIRouter(prefix="/api/wallets", tags=["investigation readiness"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
MIN_PUBLISHABLE_CASES = 100
MIN_CLASS_SUPPORT = 30
MIN_INDEPENDENT_SOURCES = 2


def _json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


@router.get("/{address}/readiness")
async def wallet_readiness(
    address: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    wallet = address.lower()

    try:
        sync = await repo.db.fetchrow(
            """SELECT provider,categories,outgoing_complete,incoming_complete,
                      oldest_block,newest_block,records_cached,updated_at
               FROM wallet_history_sync
               WHERE chain_id=1 AND wallet_address=$1
               ORDER BY updated_at DESC LIMIT 1""",
            wallet,
        )
    except Exception:
        sync = None

    try:
        evaluation = await repo.db.fetchrow(
            """SELECT id,sample_size,metrics,label_sources,created_at
               FROM detection_evaluations ORDER BY created_at DESC LIMIT 1"""
        )
    except Exception:
        evaluation = None

    metrics = _json(evaluation.get("metrics")) if evaluation else {}
    raw_sources = evaluation.get("label_sources") if evaluation else []
    if isinstance(raw_sources, str):
        try:
            raw_sources = json.loads(raw_sources)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_sources = []
    sources = sorted({str(item) for item in (raw_sources or []) if str(item).strip()})
    sample_size = int(evaluation.get("sample_size") or 0) if evaluation else 0
    positive_support = int(metrics.get("positive_support") or 0)
    negative_support = int(metrics.get("negative_support") or 0)
    evaluation_publishable = bool(
        sample_size >= MIN_PUBLISHABLE_CASES
        and positive_support >= MIN_CLASS_SUPPORT
        and negative_support >= MIN_CLASS_SUPPORT
        and len(sources) >= MIN_INDEPENDENT_SOURCES
    )

    provider_complete = bool(
        sync and sync.get("outgoing_complete") and sync.get("incoming_complete")
    )
    categories = sync.get("categories") if sync else []
    if isinstance(categories, str):
        try:
            categories = json.loads(categories)
        except (TypeError, ValueError, json.JSONDecodeError):
            categories = []

    ml = await model_status()
    external = await external_benchmark_summary(repo.db)

    blockers = []
    if not provider_complete:
        blockers.append("selected_provider_history_not_fully_paginated")
    if not evaluation_publishable:
        blockers.append("detection_evaluation_not_publishable")
    if not ml.get("production_quality_gate_passed"):
        blockers.append("supervised_ml_not_production_promoted")

    return {
        "address": wallet,
        "chain_id": 1,
        "overall": {
            "status": "review_ready" if provider_complete else "bounded_evidence_only",
            "production_intelligence_ready": not blockers,
            "blockers": blockers,
        },
        "data_completeness": {
            "provider": sync.get("provider") if sync else None,
            "selected_categories": categories or [],
            "selected_category_history_complete": provider_complete,
            "outgoing_complete": bool(sync and sync.get("outgoing_complete")),
            "incoming_complete": bool(sync and sync.get("incoming_complete")),
            "oldest_block_cached": sync.get("oldest_block") if sync else None,
            "newest_block_cached": sync.get("newest_block") if sync else None,
            "records_cached": int(sync.get("records_cached") or 0) if sync else 0,
            "last_synced_at": sync.get("updated_at") if sync else None,
            "full_evm_execution_complete": False,
            "full_chain_archive_complete": False,
            "meaning": "Complete means pagination exhausted only for the selected provider transfer categories. It never means every EVM internal call, state change, or all Ethereum history has been reconstructed.",
        },
        "detection_validation": {
            "evaluation_exists": bool(evaluation),
            "publishable": evaluation_publishable,
            "sample_size": sample_size,
            "positive_support": positive_support,
            "negative_support": negative_support,
            "independent_label_sources": sources,
            "source_count": len(sources),
            "minimum_publishable_cases": MIN_PUBLISHABLE_CASES,
            "minimum_class_support": MIN_CLASS_SUPPORT,
            "minimum_independent_sources": MIN_INDEPENDENT_SOURCES,
            "precision": metrics.get("precision") if evaluation_publishable else None,
            "recall": metrics.get("recall") if evaluation_publishable else None,
            "f1": metrics.get("f1") if evaluation_publishable else None,
            "false_positive_rate": metrics.get("false_positive_rate") if evaluation_publishable else None,
            "reason": None if evaluation_publishable else "Metrics stay non-publishable until sample size, both-class support, and independent source diversity gates are satisfied.",
        },
        "external_benchmark": {
            "source": external.get("source"),
            "sample_size": external.get("sample_size", 0),
            "positives": external.get("positives", 0),
            "negatives": external.get("negatives", 0),
            "representative": False,
            "role": "independent smoke/training benchmark; not a live-Ethereum prevalence estimate",
        },
        "machine_learning": {
            "supervised_model_available": bool(ml.get("available")),
            "deployment_mode": ml.get("deployment_mode"),
            "production_quality_gate_passed": bool(ml.get("production_quality_gate_passed")),
            "dataset_rows": ml.get("dataset_rows"),
            "test_metrics": ml.get("test_metrics") if ml.get("production_quality_gate_passed") else None,
            "behavioral_anomaly_endpoint": "/api/ml/anomaly/{tx_hash}",
            "policy": "Unsupervised anomaly output and supervised shadow output remain separate from the auditable production rule score until validated promotion criteria are met.",
        },
    }
