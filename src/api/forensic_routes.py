"""Evidence-backed forensic analysis over cached investigated-wallet transfers."""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.forensics.wallet_analysis import analyze_wallet

router = APIRouter(prefix="/api/wallets", tags=["forensic analysis"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


@router.get("/{address}/forensics")
async def wallet_forensics(
    address: str,
    limit: int = Query(1500, ge=50, le=5000),
    rapid_minutes: int = Query(30, ge=1, le=1440),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    wallet = address.lower()
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
        raise HTTPException(
            status_code=503,
            detail="Forensic evidence cache unavailable; sync wallet history first",
        ) from exc

    analysis = analyze_wallet(wallet, [dict(row) for row in rows], rapid_minutes=rapid_minutes)
    sync = await repo.db.fetchrow(
        """SELECT provider,categories,outgoing_complete,incoming_complete,
                  records_cached,oldest_block,newest_block,updated_at
           FROM wallet_history_sync
           WHERE chain_id=1 AND wallet_address=$1
           ORDER BY updated_at DESC LIMIT 1""",
        wallet,
    )
    provider_complete = bool(sync and sync.get("outgoing_complete") and sync.get("incoming_complete"))
    return {
        **analysis,
        "coverage": {
            "rows_examined": len(rows),
            "query_limit": limit,
            "query_truncated": len(rows) >= limit,
            "provider": sync.get("provider") if sync else None,
            "selected_categories": sync.get("categories") if sync else [],
            "selected_category_history_complete": provider_complete,
            "records_cached": int(sync.get("records_cached") or 0) if sync else 0,
            "oldest_block_cached": sync.get("oldest_block") if sync else None,
            "newest_block_cached": sync.get("newest_block") if sync else None,
            "last_synced_at": sync.get("updated_at") if sync else None,
            "full_evm_execution_complete": False,
        },
        "readiness": "stronger_evidence" if provider_complete and len(rows) < limit else "bounded_evidence",
        "warning": "Findings are descriptive graph/temporal observations over cached evidence, not fraud or ownership conclusions.",
    }
