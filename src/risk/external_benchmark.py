"""Independent external benchmark for ChainScope transaction triage.

The benchmark is deliberately kept separate from training/scoring data. It pulls a
small balanced smoke-test sample from the public Stepan4545/tx_scam Hugging Face
dataset. These labels are external to ChainScope and are never imported into the
risk engine as intelligence signals.

This sample is *not* claimed to be representative of current Ethereum traffic. It
exists to make false positives, missed alerts and abstentions measurable while a
larger, time-separated validation corpus is assembled.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

import httpx
from loguru import logger

from src.risk.evaluation import evaluate_predictions
from src.risk.evidence_v2 import assess_evidence

DATASET_ID = "Stepan4545/tx_scam"
SOURCE_NAME = "huggingface:Stepan4545/tx_scam"
SOURCE_REFERENCE = "https://huggingface.co/datasets/Stepan4545/tx_scam"
FILTER_URL = "https://datasets-server.huggingface.co/filter"
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def ensure_external_benchmark_schema(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS external_detection_benchmark_cases (
            source TEXT NOT NULL,
            source_row_idx BIGINT NOT NULL,
            tx_hash VARCHAR(66) NOT NULL,
            label SMALLINT NOT NULL CHECK (label IN (0,1)),
            from_address VARCHAR(42),
            to_address VARCHAR(42),
            value_wei_text TEXT,
            gas BIGINT,
            gas_price_text TEXT,
            block_timestamp_text TEXT,
            block_number BIGINT,
            category TEXT,
            source_reference TEXT NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source, source_row_idx),
            UNIQUE (source, tx_hash)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_detection_benchmark_label
        ON external_detection_benchmark_cases(source, label)
        """
    )


def _integer_text(value: object) -> str:
    """Normalize viewer numeric values without pretending float precision is exact."""
    if value is None:
        return "0"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    return str(int(number))


def _normalize_row(item: Dict[str, Any], expected_label: int) -> Dict[str, Any] | None:
    row = item.get("row") if isinstance(item, dict) else None
    if not isinstance(row, dict):
        return None
    tx_hash = str(row.get("tx_hash") or "").lower()
    try:
        label = int(row.get("label"))
    except (TypeError, ValueError):
        return None
    if not TX_HASH.fullmatch(tx_hash) or label != expected_label:
        return None

    from_address = str(row.get("from_address") or "").lower()
    to_address = str(row.get("to_address") or "").lower()
    if from_address and not ADDRESS.fullmatch(from_address):
        from_address = ""
    if to_address and not ADDRESS.fullmatch(to_address):
        to_address = ""

    try:
        source_row_idx = int(item.get("row_idx"))
    except (TypeError, ValueError):
        return None
    try:
        gas = int(Decimal(str(row.get("gas") or 0)))
    except (InvalidOperation, ValueError, TypeError):
        gas = 0
    try:
        block_number = int(row.get("block_number") or 0)
    except (TypeError, ValueError):
        block_number = 0

    return {
        "source_row_idx": source_row_idx,
        "tx_hash": tx_hash,
        "label": label,
        "from_address": from_address or None,
        "to_address": to_address or None,
        "value_wei_text": _integer_text(row.get("value")),
        "gas": gas,
        "gas_price_text": _integer_text(row.get("gas_price")),
        "block_timestamp_text": str(row.get("block_timestamp") or "") or None,
        "block_number": block_number,
        "category": str(row.get("owasp_category") or "none"),
    }


async def _fetch_label_slice(label: int, length: int) -> tuple[list[Dict[str, Any]], int | None]:
    params = {
        "dataset": DATASET_ID,
        "config": "default",
        "split": "train",
        "where": f'"label"={label}',
        "offset": 0,
        "length": max(1, min(100, int(length))),
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(FILTER_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("rows") if isinstance(payload, dict) else []
    normalized = []
    for item in rows or []:
        row = _normalize_row(item, label)
        if row:
            normalized.append(row)
    total = payload.get("num_rows_total") if isinstance(payload, dict) else None
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return normalized, total


async def sync_external_benchmark(db, per_class: int = 100) -> Dict[str, Any]:
    """Best-effort balanced smoke-test import from the external public dataset."""
    await ensure_external_benchmark_schema(db)
    per_class = max(1, min(100, int(per_class)))
    inserted = 0
    fetched = 0
    source_totals: dict[str, int | None] = {}

    for label in (0, 1):
        rows, total = await _fetch_label_slice(label, per_class)
        source_totals[str(label)] = total
        fetched += len(rows)
        for row in rows:
            result = await db.execute(
                """
                INSERT INTO external_detection_benchmark_cases (
                    source, source_row_idx, tx_hash, label, from_address, to_address,
                    value_wei_text, gas, gas_price_text, block_timestamp_text,
                    block_number, category, source_reference
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT (source, source_row_idx) DO UPDATE SET
                    tx_hash=EXCLUDED.tx_hash,
                    label=EXCLUDED.label,
                    from_address=EXCLUDED.from_address,
                    to_address=EXCLUDED.to_address,
                    value_wei_text=EXCLUDED.value_wei_text,
                    gas=EXCLUDED.gas,
                    gas_price_text=EXCLUDED.gas_price_text,
                    block_timestamp_text=EXCLUDED.block_timestamp_text,
                    block_number=EXCLUDED.block_number,
                    category=EXCLUDED.category,
                    source_reference=EXCLUDED.source_reference
                """,
                SOURCE_NAME,
                row["source_row_idx"],
                row["tx_hash"],
                row["label"],
                row["from_address"],
                row["to_address"],
                row["value_wei_text"],
                row["gas"],
                row["gas_price_text"],
                row["block_timestamp_text"],
                row["block_number"],
                row["category"],
                SOURCE_REFERENCE,
            )
            # asyncpg UPDATE/INSERT rowcount is not needed here: upserted rows are
            # intentionally treated as refreshed benchmark records.
            if result:
                inserted += 1

    logger.info(
        "External benchmark sync refreshed {} rows from {} ({} fetched)",
        inserted, SOURCE_NAME, fetched,
    )
    return {
        "source": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "rows_fetched": fetched,
        "rows_refreshed": inserted,
        "source_label_totals": source_totals,
        "sampling": "first up-to-100 rows per class returned by the source filter",
        "representative": False,
    }


async def external_benchmark_summary(db) -> Dict[str, Any]:
    await ensure_external_benchmark_schema(db)
    row = await db.fetchrow(
        """
        SELECT COUNT(*) AS sample_size,
               COUNT(*) FILTER (WHERE label=1) AS positives,
               COUNT(*) FILTER (WHERE label=0) AS negatives,
               MIN(imported_at) AS oldest_import,
               MAX(imported_at) AS newest_import
        FROM external_detection_benchmark_cases
        WHERE source=$1
        """,
        SOURCE_NAME,
    )
    return {
        "source": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "sample_size": int(row["sample_size"] or 0),
        "positives": int(row["positives"] or 0),
        "negatives": int(row["negatives"] or 0),
        "oldest_import": row["oldest_import"],
        "newest_import": row["newest_import"],
        "independent_from_chainscope": True,
        "representative": False,
        "sampling_note": "Balanced smoke-test subset; not a prevalence estimate for live Ethereum traffic.",
    }


async def evaluate_external_benchmark(db, scorer, threshold: int = 20) -> Dict[str, Any]:
    """Measure the current transaction-native scorer against external labels.

    Address-history and entity-enrichment signals are intentionally absent because
    this external dataset contains only transaction-native fields. The product policy
    metrics therefore preserve abstention when the available evidence is insufficient.
    """
    await ensure_external_benchmark_schema(db)
    rows = await db.fetch(
        """
        SELECT source_row_idx,tx_hash,label,from_address,to_address,value_wei_text,
               gas,gas_price_text,block_timestamp_text,block_number,category
        FROM external_detection_benchmark_cases
        WHERE source=$1
        ORDER BY label, source_row_idx
        """,
        SOURCE_NAME,
    )
    if not rows:
        return {
            "measured": False,
            "reason": "external_benchmark_not_synced",
            "source": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
        }

    policy_cases = []
    raw_score_cases = []
    score_distribution = {"0_19": 0, "20_39": 0, "40_79": 0, "80_100": 0}
    for row in rows:
        tx = {
            "hash": row["tx_hash"],
            "from_address": row.get("from_address"),
            "to_address": row.get("to_address"),
            "value": int(row.get("value_wei_text") or 0),
            "block_number": int(row.get("block_number") or 0),
        }
        scored = await scorer.score_transaction(tx, address_history=[])
        score = int(scored.get("score") or 0)
        if score < 20:
            score_distribution["0_19"] += 1
        elif score < 40:
            score_distribution["20_39"] += 1
        elif score < 80:
            score_distribution["40_79"] += 1
        else:
            score_distribution["80_100"] += 1

        assessment = assess_evidence(scored.get("factors") or [], row["tx_hash"])
        if assessment.get("assessment") == "review":
            policy_prediction = "1" if score >= threshold else "0"
        else:
            policy_prediction = "abstain"

        label = int(row["label"])
        policy_cases.append({"case_id": row["tx_hash"], "label": label, "prediction": policy_prediction})
        raw_score_cases.append({
            "case_id": row["tx_hash"],
            "label": label,
            "prediction": "1" if score >= threshold else "0",
        })

    policy_metrics = evaluate_predictions(policy_cases)
    raw_metrics = evaluate_predictions(raw_score_cases)
    return {
        "measured": True,
        "source": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "threshold": threshold,
        "sample_size": len(rows),
        "policy_metrics": policy_metrics,
        "raw_numeric_score_metrics": raw_metrics,
        "score_distribution": score_distribution,
        "evaluation_scope": "transaction-native fields only; no address-history, graph, entity, or sanctions enrichment",
        "representative": False,
        "limitations": [
            "The synced subset is intentionally balanced and is not a live-network prevalence estimate.",
            "The source dataset is external to ChainScope but has not been independently re-labelled by ChainScope.",
            "History-dependent and entity-intelligence factors cannot be reconstructed from these rows alone.",
            "Raw numeric score metrics are diagnostic only; ChainScope product policy may abstain when evidence is insufficient.",
        ],
    }
