"""
API route handlers.
Each function handles one HTTP endpoint.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.models import (
    TransactionResponse,
    TransactionListResponse,
    StatsResponse,
)
from src.api.dependencies import get_transaction_repo, get_address_repo
from src.agents.explainer import evidence_explanation
from src.risk.evidence_v2 import assess_evidence
from src.database.repositories import TransactionRepository, AddressRepository


router = APIRouter(prefix="/api", tags=["blockchain"])

FLAGGED_THRESHOLD = 20
HIGH_RISK_THRESHOLD = 40
CRITICAL_THRESHOLD = 80


def _explanation_status(explanation) -> str:
    if not isinstance(explanation, str) or not explanation.strip():
        return "none"
    text = explanation.strip()
    if text.startswith("Grounded AI explanation:"):
        return "grounded_ai"
    if text.startswith("Rule-based risk assessment:") or text.startswith("Evidence-based assessment:") or text.startswith("Evidence-based transaction review:"):
        return "deterministic"
    return "legacy_unverified"


def _format_tx(row: dict) -> TransactionResponse:
    """Convert a raw DB row into a TransactionResponse.

    Historical rows may contain missing or legacy generic explanation text. Unless the
    stored value is a currently grounded AI explanation, materialize a fresh deterministic
    explanation from the row's own transaction facts and risk evidence. This makes the
    response transaction-specific without rewriting historical database rows.
    """
    value_wei = int(row.get('value', 0))
    factors = row.get('risk_factors') or []
    if isinstance(factors, str):
        try:
            factors = json.loads(factors)
        except (ValueError, TypeError):
            factors = []
    if not isinstance(factors, list):
        factors = []
    factors = [factor for factor in factors if isinstance(factor, dict)]

    explanation = row.get('ai_explanation')
    explanation_status = _explanation_status(explanation)
    if explanation_status != "grounded_ai":
        explanation = evidence_explanation(
            {
                "hash": row['hash'],
                "from_address": row['from_address'],
                "to_address": row['to_address'],
                "value": value_wei,
                "block_number": row['block_number'],
                "risk_score": row.get('risk_score', 0),
            },
            factors,
        )
        explanation_status = "deterministic"

    return TransactionResponse(
        hash=row['hash'],
        from_address=row['from_address'],
        to_address=row['to_address'],
        value_wei=str(value_wei),
        value_eth=value_wei / 10**18,
        block_number=row['block_number'],
        timestamp=row['timestamp'],
        risk_score=row.get('risk_score', 0),
        ai_explanation=explanation,
        explanation_status=explanation_status,
        risk_factors=factors,
        evidence_assessment=assess_evidence(factors, row['hash']),
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(20, ge=1, le=100, description="Number of txs to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """List recent transactions with pagination."""
    rows = await repo.list_recent(limit=limit, offset=offset)
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
    min_score: int = Query(FLAGGED_THRESHOLD, ge=0, le=100, description="Minimum risk score"),
    limit: int = Query(50, ge=1, le=200),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """List transactions at or above the requested review threshold."""
    rows = await repo.list_flagged(min_score=min_score, limit=limit)
    return TransactionListResponse(
        transactions=[_format_tx(r) for r in rows],
        total=await repo.count_flagged(min_score=min_score),
        limit=limit,
        offset=0,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    tx_repo: TransactionRepository = Depends(get_transaction_repo),
    addr_repo: AddressRepository = Depends(get_address_repo),
):
    """Get retained-window statistics from one internally consistent threshold policy."""
    total_txs = await tx_repo.count()
    total_addrs = await addr_repo.count()

    stats = await tx_repo.db.fetchrow("""
        SELECT
            COALESCE(AVG(risk_score), 0) AS avg_score,
            COALESCE(MAX(risk_score), 0) AS max_score,
            COUNT(*) FILTER (WHERE risk_score >= $1) AS flagged,
            COUNT(*) FILTER (WHERE risk_score >= $2) AS high_risk,
            COUNT(*) FILTER (WHERE risk_score >= $3) AS critical,
            COUNT(*) FILTER (WHERE ai_explanation IS NOT NULL) AS explained,
            COUNT(*) FILTER (
                WHERE ai_explanation LIKE 'Grounded AI explanation:%'
                   OR ai_explanation LIKE 'Rule-based risk assessment:%'
                   OR ai_explanation LIKE 'Evidence-based assessment:%'
                   OR ai_explanation LIKE 'Evidence-based transaction review:%'
            ) AS grounded_explanations
        FROM transactions
    """, FLAGGED_THRESHOLD, HIGH_RISK_THRESHOLD, CRITICAL_THRESHOLD)

    return StatsResponse(
        total_transactions=total_txs,
        total_addresses=total_addrs,
        flagged_transactions=int(stats['flagged']),
        flagged_threshold=FLAGGED_THRESHOLD,
        high_risk_transactions=int(stats['high_risk']),
        high_risk_threshold=HIGH_RISK_THRESHOLD,
        critical_transactions=int(stats['critical']),
        critical_threshold=CRITICAL_THRESHOLD,
        avg_risk_score=round(float(stats['avg_score']), 2),
        max_risk_score=int(stats['max_score']),
        explained_transactions=int(stats['explained']),
        grounded_explanations=int(stats['grounded_explanations']),
    )
