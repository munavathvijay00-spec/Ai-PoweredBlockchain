"""API for independently supervised ML model lifecycle and behavioral signals."""
from __future__ import annotations

import hmac
import re
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.database.connection import get_db
from src.ml.anomaly import transaction_anomaly
from src.ml.model_registry import model_status, predict_shadow, train_and_register
from src.ml.wallet_features import extract_wallet_features
from src.utils.config import get_settings

router = APIRouter(prefix="/api/ml", tags=["independent ml"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def require_ml_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


@router.get("/status")
async def get_ml_status():
    """Public provenance/quality summary; never exposes model bytes or secrets."""
    return await model_status()


@router.post("/train", dependencies=[Depends(require_ml_key)])
async def train_model(limit: int = Query(default=5000, ge=100, le=50000)):
    """Train/register using only independent external labels."""
    try:
        return await train_and_register(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/anomaly/{tx_hash}")
async def anomaly_predict(tx_hash: str, limit: int = Query(default=3000, ge=100, le=3000)):
    """Unsupervised behavioral anomaly score over retained Ethereum activity."""
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise HTTPException(status_code=422, detail="Invalid Ethereum transaction hash")
    db = await get_db()
    return {"tx_hash": tx_hash.lower(), "behavioral_ml": await transaction_anomaly(db, tx_hash.lower(), limit=limit)}


@router.get("/wallet-features/{address}")
async def wallet_features(address: str, limit: int = Query(default=2000, ge=50, le=5000)):
    """Return label-independent graph/temporal features for future ML and model audits."""
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    wallet = address.lower()
    db = await get_db()
    try:
        rows = await db.fetch(
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
    result = extract_wallet_features(wallet, [dict(row) for row in rows])
    return {
        **result,
        "query_limit": limit,
        "query_truncated": len(rows) >= limit,
        "interpretation": "These are descriptive ML features, not a fraud score or probability of criminality.",
    }


@router.get("/shadow/{tx_hash}", dependencies=[Depends(require_ml_key)])
async def shadow_predict(tx_hash: str):
    """Run the latest registered independent model without altering risk_score."""
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise HTTPException(status_code=422, detail="Invalid Ethereum transaction hash")
    db = await get_db()
    row = await db.fetchrow("""
        SELECT t.hash, t.value, t.gas_price, t.gas_used, t.timestamp,
               t.block_number, t.risk_score,
               af.address AS from_address, at.address AS to_address
        FROM transactions t
        JOIN addresses af ON af.id=t.from_address_id
        JOIN addresses at ON at.id=t.to_address_id
        WHERE t.hash=$1
    """, tx_hash.lower())
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found in retained ChainScope data")
    try:
        ml = await predict_shadow(dict(row))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Independent ML model has not been trained and registered") from exc
    return {
        "tx_hash": tx_hash.lower(),
        "ml_shadow": ml,
        "current_rule_risk_score": int(row["risk_score"] or 0),
        "separation": "ML shadow output is intentionally not blended into the production rule-based risk score.",
    }
