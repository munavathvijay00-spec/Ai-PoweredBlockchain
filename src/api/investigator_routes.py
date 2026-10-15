"""Protected wallet-level grounded investigation endpoint."""
from __future__ import annotations

import hmac
import re
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.agents.wallet_investigator import investigate_wallet
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.forensics.wallet_analysis import analyze_wallet
from src.utils.config import get_settings

router = APIRouter(prefix="/api/wallets", tags=["grounded wallet investigator"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def require_investigator_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


@router.post("/{address}/ai-investigation", dependencies=[Depends(require_investigator_key)])
async def wallet_ai_investigation(
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
        raise HTTPException(status_code=503, detail="Wallet evidence cache unavailable") from exc

    analysis = analyze_wallet(wallet, [dict(row) for row in rows], rapid_minutes=rapid_minutes)
    result = await investigate_wallet(analysis)
    return {
        "address": wallet,
        "analysis_scope": "cached evidence only",
        "forensic_finding_count": analysis.get("finding_count", 0),
        "investigation": result,
        "warning": "AI output is accepted only when every factual statement is supported by deterministic forensic findings. Rejected output falls back to deterministic text.",
    }
