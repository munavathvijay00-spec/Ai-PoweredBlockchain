"""Out-of-band grounded AI enrichment for retained review transactions.

The live Ethereum ingest loop must never wait on an external model. This worker is
therefore designed to run separately (for example as a Railway cron service). It
selects a small bounded batch of transactions that already have recorded evidence,
asks the configured provider only to rewrite that evidence, stores the result only
when the grounding contract passes, and audits every attempt.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from loguru import logger

from src.agents.ai_audit import provider_configuration, record_ai_run
from src.agents.explainer import evidence_explanation, get_explainer
from src.database.connection import close_db, get_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.utils.config import get_settings


def _decode_factors(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    return []


def _tx_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "hash": row["hash"],
        "from_address": row["from_address"],
        "to_address": row["to_address"],
        "value": row["value"],
        "value_wei": row["value"],
        "block_number": row["block_number"],
        "risk_score": row.get("risk_score", 0),
    }


async def load_candidates(db, *, limit: int, min_score: int) -> list[Dict[str, Any]]:
    """Select only evidence-bearing rows that do not already have accepted AI text."""
    rows = await db.fetch(
        """
        SELECT
            t.hash,
            af.address AS from_address,
            at.address AS to_address,
            t.value,
            t.block_number,
            t.timestamp,
            t.risk_score,
            t.risk_factors,
            t.ai_explanation
        FROM transactions t
        JOIN addresses af ON af.id = t.from_address_id
        JOIN addresses at ON at.id = t.to_address_id
        WHERE t.risk_score >= $1
          AND t.risk_factors IS NOT NULL
          AND jsonb_typeof(t.risk_factors) = 'array'
          AND jsonb_array_length(t.risk_factors) > 0
          AND COALESCE(t.ai_explanation, '') NOT LIKE 'Grounded AI explanation:%'
        ORDER BY t.risk_score DESC, t.timestamp DESC, t.id DESC
        LIMIT $2
        """,
        max(0, min(100, int(min_score))),
        max(1, min(50, int(limit))),
    )
    return [dict(row) for row in rows]


async def enrich_once(
    db,
    *,
    explainer=None,
    limit: int | None = None,
    min_score: int | None = None,
) -> Dict[str, Any]:
    settings = get_settings()
    configuration = provider_configuration()
    batch_size = max(1, min(50, int(limit or settings.ai_enrichment_batch_size)))
    score_floor = max(0, min(100, int(min_score if min_score is not None else settings.ai_enrichment_min_score)))

    # Do not create provider traffic, audit noise, or database scans when a real
    # provider is not actually configured.
    if not configuration.get("provider_configured"):
        return {
            "provider": configuration.get("provider"),
            "model": configuration.get("model"),
            "provider_configured": False,
            "selected": 0,
            "grounded_saved": 0,
            "fallbacks": 0,
            "reason": configuration.get("configuration_reason"),
        }

    candidates = await load_candidates(db, limit=batch_size, min_score=score_floor)
    if not candidates:
        return {
            "provider": configuration.get("provider"),
            "model": configuration.get("model"),
            "provider_configured": True,
            "selected": 0,
            "grounded_saved": 0,
            "fallbacks": 0,
            "reason": "no_unexplained_evidence_bearing_transactions",
        }

    explainer = explainer or get_explainer()
    addresses = AddressRepository(db)
    repo = TransactionRepository(db, addresses)
    saved = 0
    fallbacks = 0
    status_counts: dict[str, int] = {}

    # Sequential calls are intentional: a small cron worker should favor
    # predictable provider usage and auditability over throughput.
    for row in candidates:
        factors = _decode_factors(row.get("risk_factors"))
        tx = _tx_payload(row)
        baseline = evidence_explanation(tx, factors)
        audit = await explainer.explain_with_audit(tx, factors)
        status = str(audit.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        await record_ai_run(db, tx_hash=row["hash"], baseline=baseline, audit=audit)
        if audit.get("ai_used") and audit.get("grounded"):
            explanation = str(audit.get("explanation") or "")
            if explanation.startswith("Grounded AI explanation:"):
                await repo.update_explanation(row["hash"], explanation)
                saved += 1
                continue
        fallbacks += 1

    return {
        "provider": configuration.get("provider"),
        "model": configuration.get("model"),
        "provider_configured": True,
        "selected": len(candidates),
        "grounded_saved": saved,
        "fallbacks": fallbacks,
        "status_counts": status_counts,
        "reason": "completed",
    }


async def run_once() -> Dict[str, Any]:
    db = await get_db()
    try:
        result = await enrich_once(db)
        logger.info("Grounded AI enrichment result: {}", result)
        return result
    finally:
        await close_db()


if __name__ == "__main__":
    print(asyncio.run(run_once()))
