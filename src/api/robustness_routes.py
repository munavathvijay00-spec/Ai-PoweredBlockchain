"""Production-hardening endpoints for evidence coverage, browser sessions, and export integrity."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.api.auth import (
    SESSION_COOKIE,
    Principal,
    authenticate,
    issue_viewer_session,
    require_viewer,
    viewer_session_configured,
)
from src.api.dependencies import get_transaction_repo
from src.api.analyst_routes import _ensure_schema
from src.database.repositories import TransactionRepository
from src.forensics.evidence_signing import sign_digest_hex

router = APIRouter(prefix="/api", tags=["evidence robustness"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _secure_cookie(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


@router.post("/session/viewer")
async def create_viewer_session(request: Request, response: Response):
    """Issue or refresh a short-lived HttpOnly read-only browser session."""
    if not viewer_session_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Viewer sessions are not configured",
        )

    try:
        principal = authenticate(request)
        if principal.role == "viewer" and principal.subject == "web-viewer":
            response.headers["Cache-Control"] = "no-store"
            return {"role": "viewer", "status": "active"}
    except HTTPException:
        pass

    token, exp = issue_viewer_session(subject="web-viewer", ttl_seconds=1800)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=1800,
        expires=1800,
        path="/api",
        secure=_secure_cookie(request),
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"role": "viewer", "status": "issued", "expires_at": exp}


@router.delete("/session/viewer", status_code=204)
async def clear_viewer_session(response: Response):
    response.delete_cookie(key=SESSION_COOKIE, path="/api")
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204)


@router.get("/wallets/{address}/coverage-summary")
async def wallet_coverage_summary(
    address: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Describe exactly what evidence ChainScope currently has for one wallet."""
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    wallet = address.lower()

    retained = await repo.db.fetchrow("""
        SELECT COUNT(*)::int AS tx_count,
               MIN(t.block_number) AS oldest_block,
               MAX(t.block_number) AS newest_block
        FROM transactions t
        JOIN addresses af ON af.id=t.from_address_id
        JOIN addresses at ON at.id=t.to_address_id
        WHERE af.address=$1 OR at.address=$1
    """, wallet)

    history_exists = await repo.db.fetchval("SELECT to_regclass('public.wallet_transfer_evidence') IS NOT NULL")
    sync_exists = await repo.db.fetchval("SELECT to_regclass('public.wallet_history_sync') IS NOT NULL")
    cached = {"records": 0, "oldest_block": None, "newest_block": None, "categories": []}
    sync = None
    if history_exists:
        row = await repo.db.fetchrow("""
            SELECT COUNT(*)::int AS records,
                   MIN(block_number) AS oldest_block,
                   MAX(block_number) AS newest_block,
                   COALESCE(array_agg(DISTINCT category) FILTER (WHERE category IS NOT NULL), ARRAY[]::text[]) AS categories
            FROM wallet_transfer_evidence
            WHERE chain_id=1 AND wallet_address=$1
        """, wallet)
        if row:
            cached = dict(row)
    if sync_exists:
        sync_row = await repo.db.fetchrow("""
            SELECT provider,categories,outgoing_complete,incoming_complete,
                   oldest_block,newest_block,records_cached,updated_at,last_error
            FROM wallet_history_sync
            WHERE chain_id=1 AND wallet_address=$1
            ORDER BY updated_at DESC LIMIT 1
        """, wallet)
        sync = dict(sync_row) if sync_row else None

    selected_complete = bool(sync and sync.get("outgoing_complete") and sync.get("incoming_complete"))
    if selected_complete:
        grade = "selected_categories_complete"
    elif cached.get("records"):
        grade = "partial_cached_history"
    elif retained and retained.get("tx_count"):
        grade = "retained_monitor_window_only"
    else:
        grade = "no_local_evidence"

    return {
        "address": wallet,
        "chain_id": 1,
        "coverage_grade": grade,
        "retained_native_transactions": {
            "count": int((retained or {}).get("tx_count") or 0),
            "oldest_block": (retained or {}).get("oldest_block"),
            "newest_block": (retained or {}).get("newest_block"),
            "historically_complete": False,
        },
        "indexed_history_cache": {
            "records": int(cached.get("records") or 0),
            "oldest_block": cached.get("oldest_block"),
            "newest_block": cached.get("newest_block"),
            "categories_observed": sorted(cached.get("categories") or []),
            "selected_category_history_complete": selected_complete,
            "provider": sync.get("provider") if sync else None,
            "selected_categories": sync.get("categories") if sync else [],
            "last_synced_at": sync.get("updated_at") if sync else None,
            "last_error": sync.get("last_error") if sync else None,
        },
        "full_evm_execution_complete": False,
        "coverage_statement": (
            "ChainScope distinguishes its retained native-ETH monitor window from provider-indexed wallet history. "
            "Selected-category completeness is claimed only when both provider pagination directions were exhausted. "
            "Complete EVM call traces, state transitions, and universal cross-chain history are not claimed."
        ),
    }


@router.get("/analyst/cases/{case_id}/bundle")
async def signed_case_bundle(
    case_id: str,
    principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Export a canonical, hash-addressed, optionally Ed25519-signed case bundle."""
    await _ensure_schema(repo)
    case_row = await repo.db.fetchrow("SELECT * FROM investigation_cases WHERE id=$1", case_id)
    if not case_row:
        raise HTTPException(status_code=404, detail="Case not found")
    case = dict(case_row)
    items = [dict(row) for row in await repo.db.fetch("""
        SELECT id,item_type,item_key,note,added_by,created_at
        FROM investigation_case_items WHERE case_id=$1 ORDER BY created_at,id
    """, case_id)]
    audit = [dict(row) for row in await repo.db.fetch("""
        SELECT id,actor,action,before_state,after_state,note,created_at
        FROM investigation_case_audit WHERE case_id=$1 ORDER BY created_at,id
    """, case_id)]

    tx_hashes = sorted({item["item_key"] for item in items if item["item_type"] == "transaction"})
    transactions = []
    if tx_hashes:
        transactions = [dict(row) for row in await repo.db.fetch("""
            SELECT t.hash,t.block_number,t.value::text AS value_wei,t.risk_score,t.risk_factors,
                   af.address AS from_address,at.address AS to_address
            FROM transactions t
            JOIN addresses af ON af.id=t.from_address_id
            JOIN addresses at ON at.id=t.to_address_id
            WHERE t.hash=ANY($1::text[])
            ORDER BY t.block_number,t.hash
        """, tx_hashes)]

    resolved = {row["hash"] for row in transactions}
    generated_at = datetime.now(timezone.utc).isoformat()
    body = {
        "schema_version": "chainscope.evidence-bundle.v2",
        "generated_at": generated_at,
        "generated_for": {"subject": principal.subject, "role": principal.role},
        "chain_id": 1,
        "case": case,
        "evidence_items": items,
        "transactions": transactions,
        "audit_timeline": audit,
        "transaction_references": [
            {"tx_hash": tx_hash, "url": f"https://etherscan.io/tx/{tx_hash}", "resolved_locally": tx_hash in resolved}
            for tx_hash in tx_hashes
        ],
        "coverage": {
            "requested_transaction_items": len(tx_hashes),
            "resolved_transaction_items": len(transactions),
            "unresolved_transaction_items": sorted(set(tx_hashes) - resolved),
            "full_chain_completeness_claimed": False,
            "statement": "Bundle includes case evidence currently available to ChainScope. It does not claim complete Ethereum or cross-chain history.",
        },
        "verification": {
            "canonicalization": "UTF-8 JSON; keys sorted; separators ',' ':'; generated_at included in bundle digest",
            "public_transaction_verifier": "https://etherscan.io/tx/{tx_hash}",
        },
    }
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    body["integrity"] = {
        "hash_algorithm": "sha256",
        "bundle_sha256": digest,
        "signature": sign_digest_hex(digest),
    }
    return body
