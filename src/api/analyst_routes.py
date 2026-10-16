from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/analyst", tags=["analyst-workflow"])

ReviewStatus = Literal["unreviewed", "confirmed", "false_positive", "escalated", "needs_review"]


class ReviewAction(BaseModel):
    status: ReviewStatus
    actor: str = Field("local_analyst", min_length=1, max_length=120)
    assignee: str | None = Field(None, max_length=120)
    note: str | None = Field(None, max_length=2000)


class ClusterReviewAction(ReviewAction):
    hashes: list[str] = Field(min_length=1, max_length=500)


class AuditEvent(BaseModel):
    action: Literal["export_evidence", "view_evidence", "view_rule", "open_details"]
    actor: str = Field("local_analyst", min_length=1, max_length=120)
    note: str | None = Field(None, max_length=2000)


async def _ensure_schema(repo: TransactionRepository):
    await repo.db.execute("""
        CREATE TABLE IF NOT EXISTS transaction_reviews (
            tx_hash text PRIMARY KEY,
            status text NOT NULL DEFAULT 'unreviewed',
            assignee text,
            note text,
            updated_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)
    await repo.db.execute("""
        CREATE TABLE IF NOT EXISTS transaction_review_audit (
            id bigserial PRIMARY KEY,
            tx_hash text NOT NULL,
            actor text NOT NULL,
            action text NOT NULL,
            previous_status text,
            new_status text,
            assignee text,
            note text,
            created_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)
    await repo.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_transaction_review_audit_hash_time
        ON transaction_review_audit (tx_hash, created_at DESC)
    """)


async def _save_one(repo: TransactionRepository, tx_hash: str, action: ReviewAction):
    exists = await repo.get_by_hash(tx_hash)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_hash}")

    previous = await repo.db.fetchrow(
        "SELECT status, assignee, note FROM transaction_reviews WHERE tx_hash=$1",
        tx_hash,
    )
    previous_status = previous["status"] if previous else "unreviewed"
    row = await repo.db.fetchrow("""
        INSERT INTO transaction_reviews (tx_hash, status, assignee, note, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (tx_hash) DO UPDATE SET
            status=EXCLUDED.status,
            assignee=EXCLUDED.assignee,
            note=EXCLUDED.note,
            updated_at=NOW()
        RETURNING tx_hash, status, assignee, note, updated_at
    """, tx_hash, action.status, action.assignee, action.note)
    await repo.db.execute("""
        INSERT INTO transaction_review_audit
            (tx_hash, actor, action, previous_status, new_status, assignee, note)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, tx_hash, action.actor, "review_status_changed", previous_status,
         action.status, action.assignee, action.note)
    return dict(row)


@router.get("/transactions/{tx_hash}")
async def get_review(tx_hash: str, repo: TransactionRepository = Depends(get_transaction_repo)):
    await _ensure_schema(repo)
    row = await repo.db.fetchrow(
        "SELECT tx_hash, status, assignee, note, updated_at FROM transaction_reviews WHERE tx_hash=$1",
        tx_hash,
    )
    if not row:
        return {"tx_hash": tx_hash, "status": "unreviewed", "assignee": None, "note": None, "updated_at": None}
    return dict(row)


@router.post("/transactions/{tx_hash}")
async def save_review(tx_hash: str, action: ReviewAction,
                      repo: TransactionRepository = Depends(get_transaction_repo)):
    await _ensure_schema(repo)
    async with repo.db.transaction():
        return await _save_one(repo, tx_hash, action)


@router.post("/clusters/review")
async def save_cluster_review(action: ClusterReviewAction,
                              repo: TransactionRepository = Depends(get_transaction_repo)):
    """Apply one human decision to the exact transaction hashes represented by a cluster."""
    await _ensure_schema(repo)
    unique_hashes = list(dict.fromkeys(action.hashes))
    review = ReviewAction(
        status=action.status,
        actor=action.actor,
        assignee=action.assignee,
        note=action.note,
    )
    saved = []
    async with repo.db.transaction():
        for tx_hash in unique_hashes:
            saved.append(await _save_one(repo, tx_hash, review))
    return {
        "status": action.status,
        "reviewed_transactions": len(saved),
        "hashes": unique_hashes,
        "assignee": action.assignee,
        "actor": action.actor,
    }


@router.post("/transactions/{tx_hash}/events")
async def record_audit_event(tx_hash: str, event: AuditEvent,
                             repo: TransactionRepository = Depends(get_transaction_repo)):
    exists = await repo.get_by_hash(tx_hash)
    if not exists:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _ensure_schema(repo)
    current = await repo.db.fetchrow(
        "SELECT status FROM transaction_reviews WHERE tx_hash=$1", tx_hash
    )
    status = current["status"] if current else "unreviewed"
    row = await repo.db.fetchrow("""
        INSERT INTO transaction_review_audit
            (tx_hash, actor, action, previous_status, new_status, note)
        VALUES ($1, $2, $3, $4, $4, $5)
        RETURNING id, tx_hash, actor, action, previous_status, new_status, note, created_at
    """, tx_hash, event.actor, event.action, status, event.note)
    return dict(row)


@router.get("/transactions/{tx_hash}/audit")
async def get_audit_log(
    tx_hash: str,
    limit: int = Query(100, ge=1, le=500),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    rows = await repo.db.fetch("""
        SELECT id, tx_hash, actor, action, previous_status, new_status,
               assignee, note, created_at
        FROM transaction_review_audit
        WHERE tx_hash=$1
        ORDER BY created_at DESC, id DESC
        LIMIT $2
    """, tx_hash, limit)
    return {"tx_hash": tx_hash, "events": [dict(row) for row in rows]}
