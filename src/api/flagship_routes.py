"""Protected flagship case packaging for reproducible ChainScope demonstrations."""
from __future__ import annotations

import hmac
import json
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.agents.wallet_investigator import investigate_wallet
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.forensics.investigation_package import build_package
from src.forensics.run_store import latest_package, latest_run
from src.forensics.wallet_analysis import analyze_wallet
from src.ml.anomaly import transaction_anomaly
from src.ml.model_registry import model_status
from src.ml.wallet_features import extract_wallet_features
from src.utils.config import get_settings

router = APIRouter(prefix="/api/flagship", tags=["flagship investigation"])
CASES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "flagship_cases.json"


async def require_flagship_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


def _load_cases() -> dict:
    try:
        payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="Flagship case registry unavailable") from exc
    return payload if isinstance(payload, dict) else {"cases": []}


def _find_case(case_id: str) -> dict:
    for item in _load_cases().get("cases") or []:
        if str(item.get("case_id")) == case_id:
            return item
    raise HTTPException(status_code=404, detail="Unknown flagship case")


@router.get("/cases")
async def list_flagship_cases():
    payload = _load_cases()
    return {
        "schema_version": payload.get("schema_version", 1),
        "chain_id": payload.get("chain_id", 1),
        "cases": [
            {
                "case_id": item.get("case_id"),
                "address": item.get("address"),
                "external_publisher": (item.get("external_attribution") or {}).get("publisher"),
                "incident": (item.get("external_attribution") or {}).get("incident"),
            }
            for item in payload.get("cases") or []
        ],
    }


@router.get("/{case_id}/latest")
async def latest_flagship_summary(
    case_id: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    _find_case(case_id)
    run = await latest_run(repo.db, case_id)
    if not run:
        return {
            "case_id": case_id,
            "available": False,
            "status": "not_run_yet",
        }
    return {
        "available": True,
        **run,
        "package_endpoint": f"/api/flagship/{case_id}/latest-package",
        "note": "This is a persisted run summary. Full package access requires the API key.",
    }


@router.get("/{case_id}/latest-package", dependencies=[Depends(require_flagship_key)])
async def latest_flagship_package(
    case_id: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    _find_case(case_id)
    package = await latest_package(repo.db, case_id)
    if not package:
        raise HTTPException(status_code=404, detail="No persisted flagship package is available")
    return package


@router.post("/{case_id}/package", dependencies=[Depends(require_flagship_key)])
async def flagship_package(
    case_id: str,
    include_ai: bool = Query(True),
    limit: int = Query(3000, ge=100, le=5000),
    rapid_minutes: int = Query(30, ge=1, le=1440),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    case = _find_case(case_id)
    wallet = str(case.get("address") or "").lower()

    try:
        rows = await repo.db.fetch(
            """SELECT evidence_key,tx_hash,category,direction,from_address,to_address,
                      asset,value_text,token_id,contract_address,block_number,
                      block_timestamp,evidence_url
               FROM wallet_transfer_evidence
               WHERE chain_id=1 AND (
                   wallet_address=$1 OR from_address=$1 OR to_address=$1
               )
               ORDER BY block_number ASC NULLS LAST, block_timestamp ASC NULLS LAST
               LIMIT $2""",
            wallet, limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Wallet evidence cache unavailable; deep-sync the case first") from exc

    evidence = [dict(row) for row in rows]
    forensics = analyze_wallet(wallet, evidence, rapid_minutes=rapid_minutes)
    behavior = extract_wallet_features(wallet, evidence)

    sync = await repo.db.fetchrow(
        """SELECT provider,categories,outgoing_complete,incoming_complete,records_cached,
                  oldest_block,newest_block,updated_at
           FROM wallet_history_sync
           WHERE chain_id=1 AND wallet_address=$1
           ORDER BY updated_at DESC LIMIT 1""",
        wallet,
    )
    provider_complete = bool(sync and sync.get("outgoing_complete") and sync.get("incoming_complete"))
    coverage = {
        "provider": sync.get("provider") if sync else None,
        "selected_categories": sync.get("categories") if sync else [],
        "selected_category_history_complete": provider_complete,
        "outgoing_complete": bool(sync and sync.get("outgoing_complete")),
        "incoming_complete": bool(sync and sync.get("incoming_complete")),
        "records_cached": int(sync.get("records_cached") or 0) if sync else 0,
        "rows_exported": len(evidence),
        "query_limit": limit,
        "query_truncated": len(evidence) >= limit,
        "oldest_block_cached": sync.get("oldest_block") if sync else None,
        "newest_block_cached": sync.get("newest_block") if sync else None,
        "last_synced_at": sync.get("updated_at") if sync else None,
        "full_evm_execution_complete": False,
        "full_chain_archive_complete": False,
    }

    try:
        entity_rows = await repo.db.fetch(
            """SELECT source,entity_id,entity_name,entity_type,confidence,
                      source_url,evidence,verified_at,expires_at
               FROM entity_attributions
               WHERE chain_id=1 AND address=$1
                 AND (expires_at IS NULL OR expires_at > NOW())
               ORDER BY confidence DESC,verified_at DESC""",
            wallet,
        )
        entity_intelligence = {
            "status": "source_attributed_match" if entity_rows else "no_local_match",
            "matches": [dict(row) for row in entity_rows],
            "warning": "No local match is not evidence that no attribution exists elsewhere.",
        }
    except Exception:
        entity_intelligence = {"status": "unavailable", "matches": []}

    recent_tx = await repo.db.fetchrow(
        """SELECT t.hash
           FROM transactions t
           JOIN addresses af ON af.id=t.from_address_id
           JOIN addresses at ON at.id=t.to_address_id
           WHERE af.address=$1 OR at.address=$1
           ORDER BY t.block_number DESC,t.id DESC LIMIT 1""",
        wallet,
    )
    if recent_tx:
        anomaly = await transaction_anomaly(repo.db, recent_tx["hash"])
        anomaly = {"tx_hash": recent_tx["hash"], **anomaly}
    else:
        anomaly = {
            "available": False,
            "status": "no_retained_native_transaction_for_wallet",
            "interpretation": "No transaction-level anomaly score is inferred from historical provider evidence alone.",
        }

    ml = await model_status()
    supervised_ml = {
        "available": bool(ml.get("available")),
        "deployment_mode": ml.get("deployment_mode"),
        "production_quality_gate_passed": bool(ml.get("production_quality_gate_passed")),
        "dataset_rows": ml.get("dataset_rows"),
        "test_metrics": ml.get("test_metrics") if ml.get("production_quality_gate_passed") else None,
        "policy": "Model status only; no wallet criminality label is inferred by this package endpoint.",
    }

    ai = await investigate_wallet(forensics) if include_ai else {
        "status": "disabled_for_export",
        "ai_used": False,
        "grounded": True,
    }

    package = build_package(
        case=case,
        coverage=coverage,
        evidence=evidence,
        forensics=forensics,
        entity_intelligence=entity_intelligence,
        wallet_behavior_features=behavior,
        transaction_anomaly=anomaly,
        supervised_ml=supervised_ml,
        ai_investigation=ai,
    )
    blockers = []
    if not provider_complete:
        blockers.append("selected_provider_history_not_fully_paginated")
    if len(evidence) >= limit:
        blockers.append("export_query_limit_reached")
    if not ai.get("grounded", True):
        blockers.append("ai_output_not_grounded")
    package["readiness"] = {
        "judge_demo_ready": not blockers,
        "blockers": blockers,
        "meaning": "Judge-demo ready means selected transfer categories were exhausted, the export was not truncated, and accepted AI output remained grounded. It does not mean complete EVM reconstruction.",
    }
    return package
