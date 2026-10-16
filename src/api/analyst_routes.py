from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/analyst", tags=["analyst-workflow"])


class ReviewAction(BaseModel):
    status: Literal["unreviewed", "confirmed", "false_positive", "escalated", "needs_review"]
    assignee: str | None = Field(None, max_length=120)
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
async def save_review(tx_hash: str, action: ReviewAction, repo: TransactionRepository = Depends(get_transaction_repo)):
    exists = await repo.get_by_hash(tx_hash)
    if not exists:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _ensure_schema(repo)
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
    return dict(row)
