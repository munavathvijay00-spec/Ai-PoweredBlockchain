"""Source-attributed entity intelligence.

No attribution is inferred from transfer behavior. Every returned label carries a
source, entity identifier, confidence scope, and optional evidence URL.
"""
import hmac
import json
import re
from urllib.parse import urlsplit
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.metrics import entity_lookup_total
from src.utils.config import get_settings

router = APIRouter(prefix="/api/entities", tags=["entity intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def require_entity_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


class EntityAttribution(BaseModel):
    address: str
    source: str = Field(min_length=2, max_length=100)
    entity_id: str = Field(min_length=1, max_length=200)
    entity_name: str = Field(min_length=1, max_length=250)
    entity_type: Literal[
        "exchange", "bridge", "mixer", "protocol", "sanctions", "scam",
        "phishing", "exploit", "custodian", "service", "contract", "other",
    ]
    confidence: float = Field(ge=0, le=1)
    source_url: str | None = Field(default=None, max_length=2000)
    evidence: dict = Field(default_factory=dict)


def _safe_source_url(value: str | None):
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=422, detail="source_url must be HTTPS")
    return value


async def _require_schema(repo: TransactionRepository):
    exists = await repo.db.fetchval("SELECT to_regclass('entity_attributions') IS NOT NULL")
    if not exists:
        raise HTTPException(
            status_code=503,
            detail="Entity attribution schema not initialized; apply scripts/intelligence_v2.sql",
        )


@router.get("/quality/summary")
async def entity_quality_summary(repo: TransactionRepository = Depends(get_transaction_repo)):
    """Report intelligence breadth/provenance without pretending absence means safety."""
    await _require_schema(repo)
    totals = await repo.db.fetchrow(
        """SELECT COUNT(*) AS records,
                  COUNT(DISTINCT address) AS unique_addresses,
                  COUNT(DISTINCT source) AS source_count,
                  COUNT(DISTINCT entity_type) AS type_count,
                  AVG(confidence)::float AS average_confidence,
                  MIN(verified_at) AS oldest_verified_at,
                  MAX(verified_at) AS newest_verified_at,
                  COUNT(*) FILTER (WHERE source_url IS NOT NULL) AS sourced_records,
                  COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at <= NOW()) AS expired_records
           FROM entity_attributions
           WHERE chain_id=1"""
    )
    by_source = await repo.db.fetch(
        """SELECT source,COUNT(*) AS records,COUNT(DISTINCT address) AS unique_addresses,
                  AVG(confidence)::float AS average_confidence,MAX(verified_at) AS newest_verified_at
           FROM entity_attributions
           WHERE chain_id=1 AND (expires_at IS NULL OR expires_at > NOW())
           GROUP BY source ORDER BY records DESC, source"""
    )
    by_type = await repo.db.fetch(
        """SELECT entity_type,COUNT(*) AS records,COUNT(DISTINCT address) AS unique_addresses
           FROM entity_attributions
           WHERE chain_id=1 AND (expires_at IS NULL OR expires_at > NOW())
           GROUP BY entity_type ORDER BY records DESC, entity_type"""
    )
    records = int(totals["records"] or 0)
    sourced = int(totals["sourced_records"] or 0)
    source_count = int(totals["source_count"] or 0)
    unique_addresses = int(totals["unique_addresses"] or 0)
    provenance_ratio = (sourced / records) if records else 0.0
    breadth = "broad" if unique_addresses >= 10000 and source_count >= 5 else "moderate" if unique_addresses >= 1000 and source_count >= 3 else "limited"
    return {
        "chain_id": 1,
        "records": records,
        "unique_addresses": unique_addresses,
        "source_count": source_count,
        "entity_type_count": int(totals["type_count"] or 0),
        "average_confidence": totals["average_confidence"],
        "source_url_coverage": round(provenance_ratio, 6),
        "oldest_verified_at": totals["oldest_verified_at"],
        "newest_verified_at": totals["newest_verified_at"],
        "expired_records": int(totals["expired_records"] or 0),
        "breadth": breadth,
        "by_source": [dict(row) for row in by_source],
        "by_type": [dict(row) for row in by_type],
        "quality_policy": {
            "source_attribution_required": True,
            "address_level_only": True,
            "no_behavioral_identity_inference": True,
            "no_match_means_safe": False,
        },
        "warning": "Entity coverage is bounded by loaded sources. A no-match result is not evidence that an address is benign, anonymous, or unattributed elsewhere.",
    }


@router.get("")
async def search_entities(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _require_schema(repo)
    rows = await repo.db.fetch(
        """SELECT address, source, entity_id, entity_name, entity_type,
                  confidence, source_url, verified_at
           FROM entity_attributions
           WHERE chain_id=1
             AND (entity_name ILIKE $1 OR entity_id ILIKE $1 OR address = lower($2))
             AND (expires_at IS NULL OR expires_at > NOW())
           ORDER BY confidence DESC, verified_at DESC
           LIMIT $3""",
        f"%{q}%", q, limit,
    )
    return {"query": q, "results": rows, "count": len(rows)}


@router.get("/{address}")
async def entity_by_address(
    address: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    await _require_schema(repo)
    normalized = address.lower()
    rows = await repo.db.fetch(
        """SELECT source, entity_id, entity_name, entity_type, confidence,
                  attribution_scope, source_url, evidence, verified_at, expires_at
           FROM entity_attributions
           WHERE chain_id=1 AND address=$1
             AND (expires_at IS NULL OR expires_at > NOW())
           ORDER BY confidence DESC, verified_at DESC""",
        normalized,
    )
    if rows:
        entity_lookup_total.labels(status="match").inc()
    else:
        entity_lookup_total.labels(status="no_match").inc()
    return {
        "address": normalized,
        "chain_id": 1,
        "matches": rows,
        "match_count": len(rows),
        "status": "source_attributed_match" if rows else "no_local_match",
        "warning": (
            "No local match is not evidence that the address is anonymous, benign, or unattributed elsewhere. "
            "Attributions identify an address-level label, not beneficial ownership or intent."
        ),
    }


@router.post("/import", dependencies=[Depends(require_entity_key)])
async def import_attributions(
    items: list[EntityAttribution],
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _require_schema(repo)
    if not items or len(items) > 500:
        raise HTTPException(status_code=422, detail="Provide 1-500 attributions")
    normalized = []
    for item in items:
        if not ADDRESS.fullmatch(item.address):
            raise HTTPException(status_code=422, detail=f"Invalid Ethereum address: {item.address}")
        normalized.append((
            item.address.lower(), item.source.strip(), item.entity_id.strip(),
            item.entity_name.strip(), item.entity_type, float(item.confidence),
            _safe_source_url(item.source_url), item.evidence,
        ))

    async with repo.db.transaction():
        for address, source, entity_id, entity_name, entity_type, confidence, source_url, evidence in normalized:
            await repo.db.execute(
                """
                INSERT INTO entity_attributions (
                    chain_id, address, source, entity_id, entity_name, entity_type,
                    confidence, attribution_scope, source_url, evidence, verified_at
                ) VALUES (1,$1,$2,$3,$4,$5,$6,'address',$7,$8::jsonb,NOW())
                ON CONFLICT (chain_id,address,source,entity_id) DO UPDATE SET
                    entity_name=EXCLUDED.entity_name,
                    entity_type=EXCLUDED.entity_type,
                    confidence=EXCLUDED.confidence,
                    source_url=EXCLUDED.source_url,
                    evidence=EXCLUDED.evidence,
                    verified_at=NOW()
                """,
                address, source, entity_id, entity_name, entity_type,
                confidence, source_url, json.dumps(evidence),
            )
    return {
        "imported": len(normalized),
        "chain_id": 1,
        "policy": "source-attributed address labels only; no ownership inference",
    }
