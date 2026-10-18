from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth import Principal, require_analyst, require_viewer
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/analyst", tags=["analyst-workflow"])

ReviewStatus = Literal["unreviewed", "confirmed", "false_positive", "escalated", "needs_review"]
CaseStatus = Literal["open", "in_progress", "escalated", "closed"]
CasePriority = Literal["low", "medium", "high", "critical"]
CaseItemType = Literal["transaction", "address", "entity"]
TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class ReviewAction(BaseModel):
    status: ReviewStatus
    assignee: str | None = Field(None, max_length=120)
    note: str | None = Field(None, max_length=2000)


class ClusterReviewAction(ReviewAction):
    hashes: list[str] = Field(min_length=1, max_length=500)


class AuditEvent(BaseModel):
    action: Literal["export_evidence", "view_evidence", "view_rule", "open_details"]
    note: str | None = Field(None, max_length=2000)


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str | None = Field(None, max_length=4000)
    priority: CasePriority = "medium"
    assignee: str | None = Field(None, max_length=120)


class CaseUpdate(BaseModel):
    status: CaseStatus
    priority: CasePriority | None = None
    assignee: str | None = Field(None, max_length=120)
    note: str = Field(min_length=1, max_length=2000)


class CaseItemCreate(BaseModel):
    item_type: CaseItemType
    item_key: str = Field(min_length=1, max_length=240)
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
    await repo.db.execute("""
        CREATE TABLE IF NOT EXISTS investigation_cases (
            id text PRIMARY KEY,
            title text NOT NULL,
            description text,
            status text NOT NULL DEFAULT 'open',
            priority text NOT NULL DEFAULT 'medium',
            assignee text,
            created_by text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            updated_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)
    await repo.db.execute("""
        CREATE TABLE IF NOT EXISTS investigation_case_items (
            id bigserial PRIMARY KEY,
            case_id text NOT NULL REFERENCES investigation_cases(id) ON DELETE CASCADE,
            item_type text NOT NULL,
            item_key text NOT NULL,
            note text,
            added_by text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            UNIQUE(case_id, item_type, item_key)
        )
    """)
    await repo.db.execute("""
        CREATE TABLE IF NOT EXISTS investigation_case_audit (
            id bigserial PRIMARY KEY,
            case_id text NOT NULL REFERENCES investigation_cases(id) ON DELETE CASCADE,
            actor text NOT NULL,
            action text NOT NULL,
            before_state jsonb,
            after_state jsonb,
            note text,
            created_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)
    await repo.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_investigation_case_status_time
        ON investigation_cases (status, updated_at DESC)
    """)
    await repo.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_investigation_case_audit_case_time
        ON investigation_case_audit (case_id, created_at DESC)
    """)


async def _save_one(repo: TransactionRepository, tx_hash: str, action: ReviewAction, principal: Principal):
    exists = await repo.get_by_hash(tx_hash)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_hash}")
    previous = await repo.db.fetchrow(
        "SELECT status, assignee, note FROM transaction_reviews WHERE tx_hash=$1", tx_hash
    )
    previous_status = previous["status"] if previous else "unreviewed"
    row = await repo.db.fetchrow("""
        INSERT INTO transaction_reviews (tx_hash, status, assignee, note, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (tx_hash) DO UPDATE SET
            status=EXCLUDED.status, assignee=EXCLUDED.assignee,
            note=EXCLUDED.note, updated_at=NOW()
        RETURNING tx_hash, status, assignee, note, updated_at
    """, tx_hash, action.status, action.assignee, action.note)
    await repo.db.execute("""
        INSERT INTO transaction_review_audit
            (tx_hash, actor, action, previous_status, new_status, assignee, note)
        VALUES ($1, $2, 'review_status_changed', $3, $4, $5, $6)
    """, tx_hash, principal.subject, previous_status, action.status, action.assignee, action.note)
    result = dict(row)
    result["actor"] = principal.subject
    result["actor_role"] = principal.role
    return result


async def _case(repo: TransactionRepository, case_id: str):
    row = await repo.db.fetchrow("SELECT * FROM investigation_cases WHERE id=$1", case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return dict(row)


@router.get("/transactions/{tx_hash}")
async def get_review(tx_hash: str, repo: TransactionRepository = Depends(get_transaction_repo)):
    await _ensure_schema(repo)
    row = await repo.db.fetchrow(
        "SELECT tx_hash, status, assignee, note, updated_at FROM transaction_reviews WHERE tx_hash=$1", tx_hash
    )
    if not row:
        return {"tx_hash": tx_hash, "status": "unreviewed", "assignee": None, "note": None, "updated_at": None}
    return dict(row)


@router.post("/transactions/{tx_hash}")
async def save_review(
    tx_hash: str, action: ReviewAction,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    async with repo.db.transaction():
        return await _save_one(repo, tx_hash, action, principal)


@router.post("/clusters/review")
async def save_cluster_review(
    action: ClusterReviewAction,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    unique_hashes = list(dict.fromkeys(action.hashes))
    review = ReviewAction(status=action.status, assignee=action.assignee, note=action.note)
    saved = []
    async with repo.db.transaction():
        for tx_hash in unique_hashes:
            saved.append(await _save_one(repo, tx_hash, review, principal))
    return {
        "status": action.status, "reviewed_transactions": len(saved),
        "hashes": unique_hashes, "assignee": action.assignee,
        "actor": principal.subject, "actor_role": principal.role,
    }


@router.post("/transactions/{tx_hash}/events")
async def record_audit_event(
    tx_hash: str, event: AuditEvent,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    exists = await repo.get_by_hash(tx_hash)
    if not exists:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _ensure_schema(repo)
    current = await repo.db.fetchrow("SELECT status FROM transaction_reviews WHERE tx_hash=$1", tx_hash)
    status_value = current["status"] if current else "unreviewed"
    row = await repo.db.fetchrow("""
        INSERT INTO transaction_review_audit
            (tx_hash, actor, action, previous_status, new_status, note)
        VALUES ($1, $2, $3, $4, $4, $5)
        RETURNING id, tx_hash, actor, action, previous_status, new_status, note, created_at
    """, tx_hash, principal.subject, event.action, status_value, event.note)
    return dict(row)


@router.get("/transactions/{tx_hash}/audit")
async def get_audit_log(
    tx_hash: str, limit: int = Query(100, ge=1, le=500),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    rows = await repo.db.fetch("""
        SELECT id, tx_hash, actor, action, previous_status, new_status,
               assignee, note, created_at
        FROM transaction_review_audit
        WHERE tx_hash=$1 ORDER BY created_at DESC, id DESC LIMIT $2
    """, tx_hash, limit)
    return {"tx_hash": tx_hash, "events": [dict(row) for row in rows]}


@router.post("/cases")
async def create_case(
    payload: CaseCreate,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    case_id = str(uuid4())
    row = await repo.db.fetchrow("""
        INSERT INTO investigation_cases
            (id,title,description,status,priority,assignee,created_by)
        VALUES ($1,$2,$3,'open',$4,$5,$6)
        RETURNING *
    """, case_id, payload.title.strip(), payload.description, payload.priority, payload.assignee, principal.subject)
    await repo.db.execute("""
        INSERT INTO investigation_case_audit(case_id,actor,action,after_state,note)
        VALUES ($1,$2,'case_created',$3::jsonb,$4)
    """, case_id, principal.subject, json.dumps(dict(row), default=str), payload.description)
    return dict(row)


@router.get("/cases")
async def list_cases(
    status: CaseStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    rows = await repo.db.fetch("""
        SELECT c.*,
               COUNT(i.id)::int AS evidence_items
        FROM investigation_cases c
        LEFT JOIN investigation_case_items i ON i.case_id=c.id
        WHERE ($1::text IS NULL OR c.status=$1)
        GROUP BY c.id
        ORDER BY c.updated_at DESC
        LIMIT $2
    """, status, limit)
    return {"cases": [dict(row) for row in rows], "count": len(rows)}


@router.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    _principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    case = await _case(repo, case_id)
    items = await repo.db.fetch("""
        SELECT id,item_type,item_key,note,added_by,created_at
        FROM investigation_case_items WHERE case_id=$1 ORDER BY created_at,id
    """, case_id)
    audit = await repo.db.fetch("""
        SELECT id,actor,action,before_state,after_state,note,created_at
        FROM investigation_case_audit WHERE case_id=$1 ORDER BY created_at DESC,id DESC LIMIT 200
    """, case_id)
    return {**case, "items": [dict(row) for row in items], "audit": [dict(row) for row in audit]}


@router.post("/cases/{case_id}/items")
async def add_case_item(
    case_id: str, payload: CaseItemCreate,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    await _case(repo, case_id)
    key = payload.item_key.strip()
    if payload.item_type == "transaction":
        if not TX_HASH_RE.fullmatch(key):
            raise HTTPException(status_code=422, detail="Transaction evidence requires a valid 32-byte transaction hash")
        key = key.lower()
        # Do not record arbitrary user input as a verified transaction.
        if not await repo.get_by_hash(key):
            raise HTTPException(status_code=422, detail="Transaction not found in retained evidence; fetch and verify it before attaching")
    elif payload.item_type == "address":
        if not ADDRESS_RE.fullmatch(key):
            raise HTTPException(status_code=422, detail="Address evidence requires a valid Ethereum address")
        key = key.lower()
    else:
        key = key.strip()
    async with repo.db.transaction():
        row = await repo.db.fetchrow("""
            INSERT INTO investigation_case_items(case_id,item_type,item_key,note,added_by)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT(case_id,item_type,item_key) DO UPDATE SET note=EXCLUDED.note
            RETURNING id,case_id,item_type,item_key,note,added_by,created_at
        """, case_id, payload.item_type, key, payload.note, principal.subject)
        await repo.db.execute("""
            INSERT INTO investigation_case_audit(case_id,actor,action,after_state,note)
            VALUES ($1,$2,'evidence_added',$3::jsonb,$4)
        """, case_id, principal.subject, json.dumps(dict(row), default=str), payload.note)
        await repo.db.execute("UPDATE investigation_cases SET updated_at=NOW() WHERE id=$1", case_id)
    return dict(row)


@router.post("/cases/{case_id}/state")
async def update_case_state(
    case_id: str, payload: CaseUpdate,
    principal: Principal = Depends(require_analyst),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    before = await _case(repo, case_id)
    priority = payload.priority or before["priority"]
    assignee = payload.assignee if payload.assignee is not None else before.get("assignee")
    async with repo.db.transaction():
        row = await repo.db.fetchrow("""
            UPDATE investigation_cases SET status=$2,priority=$3,assignee=$4,updated_at=NOW()
            WHERE id=$1 RETURNING *
        """, case_id, payload.status, priority, assignee)
        await repo.db.execute("""
            INSERT INTO investigation_case_audit(case_id,actor,action,before_state,after_state,note)
            VALUES ($1,$2,'case_state_changed',$3::jsonb,$4::jsonb,$5)
        """, case_id, principal.subject, json.dumps(before, default=str), json.dumps(dict(row), default=str), payload.note)
    return dict(row)


@router.get("/cases/{case_id}/report")
async def evidence_grade_case_report(
    case_id: str,
    _principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _ensure_schema(repo)
    case = await _case(repo, case_id)
    items = [dict(row) for row in await repo.db.fetch("""
        SELECT id,item_type,item_key,note,added_by,created_at
        FROM investigation_case_items WHERE case_id=$1 ORDER BY created_at,id
    """, case_id)]
    tx_hashes = [item["item_key"] for item in items if item["item_type"] == "transaction"]
    tx_rows = []
    if tx_hashes:
        tx_rows = [dict(row) for row in await repo.db.fetch("""
            SELECT t.hash,t.block_number,t.value::text AS value_wei,t.risk_score,t.risk_factors,
                   af.address AS from_address,at.address AS to_address
            FROM transactions t
            JOIN addresses af ON af.id=t.from_address_id
            JOIN addresses at ON at.id=t.to_address_id
            WHERE t.hash=ANY($1::text[]) ORDER BY t.block_number,t.hash
        """, tx_hashes)]
    report = {
        "schema_version": "chainscope.case-report.v1",
        "case": case,
        "evidence_items": items,
        "transactions": tx_rows,
        "coverage": {
            "requested_transaction_items": len(tx_hashes),
            "resolved_transaction_items": len(tx_rows),
            "unresolved_transaction_items": sorted(set(tx_hashes) - {row["hash"] for row in tx_rows}),
            "full_chain_completeness_claimed": False,
        },
        "reproduction": {
            "transaction_source": "ChainScope retained PostgreSQL transaction records",
            "public_verifier": "https://etherscan.io/tx/{tx_hash}",
            "ordering": "block_number ASC, tx_hash ASC",
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode()
    report["integrity"] = {"algorithm": "sha256", "canonical_json_sha256": hashlib.sha256(canonical).hexdigest()}
    return report
