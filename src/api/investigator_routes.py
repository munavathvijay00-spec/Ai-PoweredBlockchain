"""Protected wallet-level evidence-grounded investigation copilot."""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Query

from src.agents.wallet_investigator import investigate_wallet
from src.api.auth import Principal, require_viewer
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.forensics.wallet_analysis import analyze_wallet

router = APIRouter(prefix="/api/wallets", tags=["grounded wallet investigator"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def _investigate(address: str, limit: int, rapid_minutes: int, repo: TransactionRepository):
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
        raise HTTPException(status_code=503, detail="Wallet evidence cache unavailable") from exc
    analysis = analyze_wallet(wallet, [dict(row) for row in rows], rapid_minutes=rapid_minutes)
    result = await investigate_wallet(analysis)
    contract = result.get("evidence_contract") or {}
    finding_index = {item.get("finding_id"): item for item in contract.get("findings") or [] if item.get("finding_id")}
    citations = {
        finding_id: {
            "title": finding.get("title"),
            "transaction_hashes": finding.get("transaction_hashes") or [],
            "evidence_urls": [f"https://etherscan.io/tx/{tx_hash}" for tx_hash in finding.get("transaction_hashes") or []],
        }
        for finding_id, finding in finding_index.items()
    }
    return wallet, analysis, result, citations


@router.post("/{address}/ai-investigation")
async def wallet_ai_investigation(
    address: str,
    limit: int = Query(1500, ge=50, le=5000),
    rapid_minutes: int = Query(30, ge=1, le=1440),
    _principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    wallet, analysis, result, citations = await _investigate(address, limit, rapid_minutes, repo)
    return {
        "address": wallet,
        "analysis_scope": "cached evidence only",
        "forensic_finding_count": analysis.get("finding_count", 0),
        "investigation": result,
        "citations": citations,
        "warning": "Every accepted AI statement must cite deterministic finding IDs. Rejected model output falls back to deterministic text.",
    }


@router.post("/{address}/copilot")
async def investigation_copilot(
    address: str,
    limit: int = Query(1500, ge=50, le=5000),
    rapid_minutes: int = Query(30, ge=1, le=1440),
    _principal: Principal = Depends(require_viewer),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Return claim-level grounded investigation output plus directly resolvable evidence citations."""
    wallet, analysis, result, citations = await _investigate(address, limit, rapid_minutes, repo)
    payload = result.get("structured_payload") or {}
    claims = []
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if isinstance(summary, dict) and summary.get("text"):
        claims.append({"kind": "summary", "text": summary["text"], "finding_ids": summary.get("finding_ids") or []})
    for claim in payload.get("claims") or [] if isinstance(payload, dict) else []:
        if isinstance(claim, dict) and claim.get("text"):
            claims.append({"kind": "claim", "text": claim["text"], "finding_ids": claim.get("finding_ids") or []})
    if not claims:
        for finding in (result.get("evidence_contract") or {}).get("findings") or []:
            claims.append({
                "kind": "deterministic_finding",
                "text": f"{finding.get('title')}: {finding.get('explanation')}",
                "finding_ids": [finding.get("finding_id")],
            })
    for claim in claims:
        claim["citations"] = [citations[fid] for fid in claim.get("finding_ids") or [] if fid in citations]
    return {
        "address": wallet,
        "mode": result.get("status"),
        "ai_used": bool(result.get("ai_used")),
        "grounded": bool(result.get("grounded")),
        "claims": claims,
        "uncertainty": payload.get("uncertainty") if isinstance(payload, dict) else "Output is limited to cached evidence and deterministic findings.",
        "evidence_contract": result.get("evidence_contract"),
        "coverage": {"records_examined": analysis.get("record_count", 0), "full_chain_completeness_claimed": False},
    }
