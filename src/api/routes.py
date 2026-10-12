"""
API route handlers.
Each function handles one HTTP endpoint.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from src.api.models import (
    TransactionResponse,
    TransactionListResponse,
    StatsResponse,
)
from src.api.dependencies import get_transaction_repo, get_address_repo
from src.database.repositories import TransactionRepository, AddressRepository


router = APIRouter(prefix="/api", tags=["blockchain"])


def _format_tx(row: dict) -> TransactionResponse:
    """Convert a raw DB row into a TransactionResponse."""
    value_wei = int(row.get('value', 0))
    return TransactionResponse(
        hash=row['hash'],
        from_address=row['from_address'],
        to_address=row['to_address'],
        value_wei=str(value_wei),
        value_eth=value_wei / 10**18,
        block_number=row['block_number'],
        timestamp=row['timestamp'],
        risk_score=row.get('risk_score', 0),
        ai_explanation=row.get('ai_explanation'),
        risk_factors=row.get('risk_factors') or [],
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(20, ge=1, le=100, description="Number of txs to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """List recent transactions with pagination."""
    rows = await repo.list_recent(limit=limit)
    total = await repo.count()

    return TransactionListResponse(
        transactions=[_format_tx(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/transactions/{tx_hash}", response_model=TransactionResponse)
async def get_transaction(
    tx_hash: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Get a single transaction by hash."""
    row = await repo.get_by_hash(tx_hash)
    if not row:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_hash} not found")
    return _format_tx(row)


@router.get("/flagged", response_model=TransactionListResponse)
async def list_flagged(
    min_score: int = Query(20, ge=0, le=100, description="Minimum risk score"),
    limit: int = Query(50, ge=1, le=200),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """List flagged (high-risk) transactions."""
    rows = await repo.list_flagged(min_score=min_score, limit=limit)
    return TransactionListResponse(
        transactions=[_format_tx(r) for r in rows],
        total=len(rows),
        limit=limit,
        offset=0,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    tx_repo: TransactionRepository = Depends(get_transaction_repo),
    addr_repo: AddressRepository = Depends(get_address_repo),
):
    """Get system-wide statistics."""
    total_txs = await tx_repo.count()
    total_addrs = await addr_repo.count()
    flagged = await tx_repo.list_flagged(min_score=20, limit=10000)

    stats = await tx_repo.db.fetchrow("""
        SELECT 
            COALESCE(AVG(risk_score), 0) AS avg_score,
            COALESCE(MAX(risk_score), 0) AS max_score,
            COUNT(CASE WHEN ai_explanation IS NOT NULL THEN 1 END) AS explained
        FROM transactions
    """)

    return StatsResponse(
        total_transactions=total_txs,
        total_addresses=total_addrs,
        flagged_transactions=len(flagged),
        avg_risk_score=round(float(stats['avg_score']), 2),
        max_risk_score=int(stats['max_score']),
        explained_transactions=int(stats['explained']),
    )