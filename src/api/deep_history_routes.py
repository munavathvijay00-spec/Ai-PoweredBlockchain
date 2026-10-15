"""Budgeted deep wallet-history synchronization.

This endpoint repeatedly advances the existing provider cursors until selected-category
pagination is exhausted or an explicit safety budget is reached. It never claims full EVM
execution completeness.
"""
from __future__ import annotations

import hmac
import re
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.api.historical_routes import sync_wallet_history
from src.database.repositories import TransactionRepository
from src.utils.config import get_settings

router = APIRouter(prefix="/api/wallets", tags=["historical wallet evidence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def require_deep_history_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


@router.post("/{address}/history/deep-sync", dependencies=[Depends(require_deep_history_key)])
async def deep_sync_wallet_history(
    address: str,
    max_batches: int = Query(6, ge=1, le=20),
    pages_per_batch: int = Query(5, ge=1, le=5),
    per_direction: int = Query(50, ge=10, le=50),
    include_internal: bool = Query(True),
    include_nfts: bool = Query(True),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    wallet = address.lower()
    batches = []
    total_fetched = 0
    total_inserted = 0
    result = None

    for batch_index in range(max_batches):
        result = await sync_wallet_history(
            address=wallet,
            pages=pages_per_batch,
            per_direction=per_direction,
            include_internal=include_internal,
            include_nfts=include_nfts,
            repo=repo,
        )
        total_fetched += int(result.get("fetched_this_request") or 0)
        total_inserted += int(result.get("new_records_cached") or 0)
        batches.append({
            "batch": batch_index + 1,
            "fetched": int(result.get("fetched_this_request") or 0),
            "inserted": int(result.get("new_records_cached") or 0),
            "outgoing_complete": bool(result.get("outgoing_complete")),
            "incoming_complete": bool(result.get("incoming_complete")),
            "records_cached": int(result.get("records_cached") or 0),
        })
        if result.get("historical_complete_for_selected_categories"):
            break
        # If the provider returned no records and no inserts while still advertising a
        # cursor, stop rather than burning quota in a potential upstream inconsistency.
        if not result.get("fetched_this_request") and not result.get("new_records_cached"):
            break

    complete = bool(result and result.get("historical_complete_for_selected_categories"))
    return {
        "address": wallet,
        "provider": result.get("provider") if result else None,
        "categories": result.get("categories") if result else [],
        "batches_run": len(batches),
        "provider_records_fetched": total_fetched,
        "new_records_cached": total_inserted,
        "records_cached": int(result.get("records_cached") or 0) if result else 0,
        "selected_category_history_complete": complete,
        "outgoing_complete": bool(result and result.get("outgoing_complete")),
        "incoming_complete": bool(result and result.get("incoming_complete")),
        "oldest_block_cached": result.get("oldest_block_cached") if result else None,
        "newest_block_cached": result.get("newest_block_cached") if result else None,
        "budget": {
            "max_batches": max_batches,
            "pages_per_batch": pages_per_batch,
            "per_direction": per_direction,
            "maximum_provider_pages_per_direction": max_batches * pages_per_batch,
        },
        "batches": batches,
        "full_evm_execution_complete": False,
        "status": "selected_provider_categories_exhausted" if complete else "budget_exhausted_or_provider_stalled",
        "warning": "Completeness means cursor exhaustion for selected provider transfer categories only. It does not mean full EVM call-trace or state-transition reconstruction.",
    }
