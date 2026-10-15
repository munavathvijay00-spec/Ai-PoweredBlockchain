"""External independent detection benchmark support.

The benchmark corpus is independent from ChainScope's own labels and detector
outputs. Metrics are scoped to the imported validation set and must never be
presented as calibrated live-Ethereum fraud probabilities.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from src.risk.evaluation import evaluate_predictions
from src.risk.evidence_v2 import assess_evidence

SOURCE_NAME = "ethereum_fraud_detection_dataset"
SOURCE_REFERENCE = "https://huggingface.co/datasets/msc-smart-contract-auditing/ethereum-fraud-detection"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
FILTER_URL = "https://datasets-server.huggingface.co/filter"
DATASET = "msc-smart-contract-auditing/ethereum-fraud-detection"
CONFIG = "default"
SPLIT = "train"


async def ensure_external_benchmark_schema(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS external_detection_benchmark_cases (
            source TEXT NOT NULL,
            source_row_idx BIGINT NOT NULL,
            tx_hash TEXT NOT NULL,
            label SMALLINT NOT NULL CHECK (label IN (0,1)),
            from_address TEXT,
            to_address TEXT,
            value_wei_text TEXT,
            gas BIGINT,
            gas_price_text TEXT,
            block_timestamp_text TEXT,
            block_number BIGINT,
            category TEXT,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source, source_row_idx),
            UNIQUE (source, tx_hash)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_detection_benchmark_label
        ON external_detection_benchmark_cases(source, label)
    """)


def _synthetic_case_hash(source_row_idx: int, row: Dict[str, Any]) -> str:
    raw = "|".join(str(row.get(key) or "") for key in (
        "from_address", "to_address", "value", "gas", "gas_price", "block_timestamp", "block_number"
    ))
    digest = hashlib.sha256(f"{SOURCE_NAME}:{source_row_idx}:{raw}".encode()).hexdigest()
    return "0x" + digest


def _normalize_external_row(source_row_idx: int, row: Dict[str, Any]) -> Dict[str, Any]:
    label = int(row.get("label") or 0)
    if label not in (0, 1):
        raise ValueError("External benchmark label must be binary")
    tx_hash = str(row.get("tx_hash") or row.get("hash") or "").strip().lower()
    if not (tx_hash.startswith("0x") and len(tx_hash) == 66):
        tx_hash = _synthetic_case_hash(source_row_idx, row)
    return {
        "source_row_idx": source_row_idx,
        "tx_hash": tx_hash,
        "label": label,
        "from_address": row.get("from_address") or row.get("from") or row.get("fromAddress"),
        "to_address": row.get("to_address") or row.get("to") or row.get("toAddress"),
        "value_wei_text": str(row.get("value_wei_text") or row.get("value") or "0"),
        "gas": int(row.get("gas") or row.get("gas_used") or 0),
        "gas_price_text": str(row.get("gas_price_text") or row.get("gas_price") or row.get("gasPrice") or "0"),
        "block_timestamp_text": str(row.get("block_timestamp_text") or row.get("block_timestamp") or row.get("timestamp") or ""),
        "block_number": int(row.get("block_number") or row.get("blockNumber") or 0),
        "category": str(row.get("category") or ""),
    }


async def _fetch_filtered_label(label: int, length: int) -> tuple[list[Dict[str, Any]], int | None]:
    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "where": f"label={int(label)}",
        "offset": 0,
        "length": length,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(FILTER_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    rows = []
    for item in payload.get("rows") or []:
        row_idx = int(item.get("row_idx") or item.get("row_index") or 0)
        row = item.get("row") or {}
        rows.append({"source_row_idx": row_idx, **row})
    total = payload.get("num_rows_total")
    return rows, int(total) if total is not None else None


async def _fetch_rows_page(offset: int, length: int = 100) -> tuple[list[Dict[str, Any]], int | None]:
    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "offset": offset,
        "length": length,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(ROWS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    rows = []
    for item in payload.get("rows") or []:
        row_idx = int(item.get("row_idx") or item.get("row_index") or 0)
        row = item.get("row") or {}
        rows.append({"source_row_idx": row_idx, **row})
    total = payload.get("num_rows_total")
    return rows, int(total) if total is not None else None


async def _fetch_balanced_rows(per_class: int) -> tuple[dict[int, list[Dict[str, Any]]], Dict[str, Any]]:
    if per_class < 1:
        raise ValueError("per_class must be positive")
    buckets: dict[int, list[Dict[str, Any]]] = {0: [], 1: []}
    meta: Dict[str, Any] = {
        "mode": "filtered",
        "filter_errors": [],
        "pages_scanned": 0,
        "dataset_rows_reported": None,
        "source_label_totals": {},
    }
    for label in (0, 1):
        try:
            rows, total = await _fetch_filtered_label(label, per_class)
            meta["source_label_totals"][str(label)] = total
            for raw in rows:
                normalized = _normalize_external_row(int(raw.pop("source_row_idx")), raw)
                if normalized["label"] == label:
                    buckets[label].append(normalized)
        except Exception as exc:
            meta["filter_errors"].append(f"label={label}:{type(exc).__name__}")

    if all(len(buckets[label]) >= per_class for label in (0, 1)):
        return {label: buckets[label][:per_class] for label in (0, 1)}, meta

    # Public dataset-server deployments do not always expose SQL filtering. Fall
    # back to deterministic sequential pages and stop as soon as both classes
    # have enough cases. This remains a balanced subset, not prevalence sampling.
    buckets = {0: [], 1: []}
    meta["mode"] = "rows_fallback"
    offset = 0
    while len(buckets[0]) < per_class or len(buckets[1]) < per_class:
        rows, total = await _fetch_rows_page(offset, 100)
        meta["pages_scanned"] += 1
        if total is not None:
            meta["dataset_rows_reported"] = total
        if not rows:
            break
        for raw in rows:
            row_idx = int(raw.pop("source_row_idx"))
            normalized = _normalize_external_row(row_idx, raw)
            label = normalized["label"]
            if len(buckets[label]) < per_class:
                buckets[label].append(normalized)
        offset += len(rows)
        if total is not None and offset >= total:
            break

    if len(buckets[0]) < per_class or len(buckets[1]) < per_class:
        raise ValueError(
            f"Could not build balanced external benchmark: "
            f"negatives={len(buckets[0])}, positives={len(buckets[1])}, requested={per_class}"
        )
    return buckets, meta


async def import_external_benchmark(db, per_class: int = 50) -> Dict[str, Any]:
    await ensure_external_benchmark_schema(db)
    buckets, fetch_meta = await _fetch_balanced_rows(per_class)
    rows = buckets[0] + buckets[1]
    refreshed = 0
    for row in rows:
        result = await db.execute(
            """
            INSERT INTO external_detection_benchmark_cases(
                source,source_row_idx,tx_hash,label,from_address,to_address,
                value_wei_text,gas,gas_price_text,block_timestamp_text,block_number,category,imported_at
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            ON CONFLICT (source,source_row_idx) DO UPDATE SET
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
                imported_at=EXCLUDED.imported_at
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
            datetime.now(timezone.utc),
        )
        if str(result).endswith(" 1"):
            refreshed += 1
    return {
        "source": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "rows_fetched": len(rows),
        "rows_refreshed": refreshed,
        "class_counts": {"0": len(buckets[0]), "1": len(buckets[1])},
        "source_label_totals": fetch_meta.get("source_label_totals"),
        "sampling": fetch_meta.get("mode"),
        "fetch_diagnostics": {
            "filter_errors": fetch_meta.get("filter_errors") or [],
            "pages_scanned": fetch_meta.get("pages_scanned", 0),
            "dataset_rows_reported": fetch_meta.get("dataset_rows_reported"),
        },
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
        """, SOURCE_NAME,
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
        "sampling_note": "Balanced external validation/training subset; not a prevalence estimate for live Ethereum traffic.",
    }


async def evaluate_external_benchmark(db, scorer, threshold: int = 20) -> Dict[str, Any]:
    await ensure_external_benchmark_schema(db)
    rows = await db.fetch(
        """
        SELECT source_row_idx,tx_hash,label,from_address,to_address,value_wei_text,
               gas,gas_price_text,block_timestamp_text,block_number,category
        FROM external_detection_benchmark_cases
        WHERE source=$1
        ORDER BY label, source_row_idx
        """, SOURCE_NAME,
    )
    evaluation_rows = []
    for row in rows:
        tx = {
            "hash": row["tx_hash"],
            "value": int(row["value_wei_text"] or 0),
            "gas": int(row["gas"] or 0),
            "gas_price": int(row["gas_price_text"] or 0),
            "block_number": int(row["block_number"] or 0),
        }
        result = await scorer.score_transaction(tx, [], is_blacklisted=False, address_age_days=None)
        evidence = assess_evidence(result.get("factors") or [], tx_hash=row["tx_hash"])
        prediction = "1" if int(result.get("score") or 0) >= threshold else "0"
        # Evidence v2 intentionally treats transfer amount/call-type facts alone
        # as insufficient for a behavioral/risk decision. Keep the benchmark on
        # that same product contract; otherwise amount-only cases silently become
        # detector decisions and overstate decision coverage/quality metrics.
        if evidence.get("assessment") == "insufficient_evidence":
            prediction = "abstain"
        evaluation_rows.append({
            "case_id": f"{SOURCE_NAME}:{row['source_row_idx']}",
            "label": int(row["label"]),
            "prediction": prediction,
        })
    metrics = evaluate_predictions(evaluation_rows)
    metrics.update({
        "source": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "threshold": threshold,
        "representative": False,
        "scope": "Transaction-native rule evidence only; address-history/entity signals are unavailable in this external corpus.",
    })
    return metrics
