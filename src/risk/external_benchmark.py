"""Independent external benchmark for ChainScope transaction triage.

The benchmark is deliberately kept separate from training/scoring data. It pulls a
balanced, bounded sample from the public Stepan4545/tx_scam Hugging Face dataset.
These labels are external to ChainScope and are never imported into the rule engine
as intelligence signals.

The dataset is still not claimed to represent current Ethereum prevalence. It exists
to make false positives, missed alerts, abstentions and ML generalization measurable.
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
ROWS_URL = "https://datasets-server.huggingface.co/rows"
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
MAX_PER_CLASS = 500


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
    if value is None:
        return "0"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    return str(int(number))


def _normalize_row(item: Dict[str, Any], expected_label: int | None = None) -> Dict[str, Any] | None:
    row = item.get("row") if isinstance(item, dict) else None
    if not isinstance(row, dict):
        return None
    tx_hash = str(row.get("tx_hash") or "").lower()
    try:
        label = int(row.get("label"))
    except (TypeError, ValueError):
        return None
    if label not in (0, 1):
        return None
    if expected_label is not None and label != expected_label:
        return None
    if not TX_HASH.fullmatch(tx_hash):
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


async def _get_json(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Dataset viewer returned a non-object response")
    return payload


async def _fetch_filtered_label(label: int, length: int) -> tuple[list[Dict[str, Any]], int | None]:
    params = {
        "dataset": DATASET_ID,
        "config": "default",
        "split": "train",
        "where": f'"label"={label}',
        "offset": 0,
        "length": max(1, min(100, int(length))),
    }
    payload = await _get_json(FILTER_URL, params)
    normalized = []
    for item in payload.get("rows") or []:
        row = _normalize_row(item, label)
        if row:
            normalized.append(row)
    total = payload.get("num_rows_total")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return normalized, total


async def _fetch_rows_page(offset: int, length: int = 100) -> tuple[list[Dict[str, Any]], int | None]:
    params = {
        "dataset": DATASET_ID,
        "config": "default",
        "split": "train",
        "offset": max(0, int(offset)),
        "length": max(1, min(100, int(length))),
    }
    payload = await _get_json(ROWS_URL, params)
    normalized = []
    for item in payload.get("rows") or []:
        row = _normalize_row(item)
        if row:
            normalized.append(row)
    total = payload.get("num_rows_total")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return normalized, total


def _add_rows(buckets: dict[int, list[Dict[str, Any]]], seen: set[str], rows, per_class: int) -> None:
    for row in rows:
        label = int(row["label"])
        tx_hash = row["tx_hash"]
        if tx_hash in seen or len(buckets[label]) >= per_class:
            continue
        seen.add(tx_hash)
        buckets[label].append(row)


async def _fetch_balanced_rows(per_class: int) -> tuple[dict[int, list[Dict[str, Any]]], dict[str, Any]]:
    buckets: dict[int, list[Dict[str, Any]]] = {0: [], 1: []}
    seen: set[str] = set()
    source_totals: dict[str, int | None] = {"0": None, "1": None}
    filter_errors: list[str] = []

    for label in (0, 1):
        try:
            rows, total = await _fetch_filtered_label(label, per_class)
            source_totals[str(label)] = total
            _add_rows(buckets, seen, rows, per_class)
        except httpx.HTTPStatusError as exc:
            status = getattr(exc.response, "status_code", None)
            filter_errors.append(f"label_{label}_http_{status or 'error'}")
        except (httpx.HTTPError, ValueError) as exc:
            filter_errors.append(f"label_{label}_{type(exc).__name__}")

    if all(len(buckets[label]) >= per_class for label in (0, 1)):
        return buckets, {"mode": "filter", "source_label_totals": source_totals, "filter_errors": filter_errors, "pages_scanned": 0}

    first_page, total_rows = await _fetch_rows_page(0, 100)
    _add_rows(buckets, seen, first_page, per_class)
    total_rows = int(total_rows or len(first_page))
    max_offset = max(0, total_rows - 100)

    # Sample more pages as the requested corpus grows while keeping startup work bounded.
    page_budget = min(48, max(16, int(per_class / 20) + 8))
    offsets = [max_offset]
    if max_offset:
        offsets.extend(int(max_offset * step / page_budget) for step in range(1, page_budget))
    offsets = list(dict.fromkeys(max(0, offset) for offset in offsets if offset != 0))

    pages_scanned = 1
    for offset in offsets:
        if all(len(buckets[label]) >= per_class for label in (0, 1)):
            break
        page, observed_total = await _fetch_rows_page(offset, 100)
        pages_scanned += 1
        if observed_total:
            total_rows = int(observed_total)
        _add_rows(buckets, seen, page, per_class)

    if not buckets[0] or not buckets[1]:
        raise RuntimeError("External benchmark fallback could not obtain both independent label classes")
    return buckets, {
        "mode": "rows_fallback",
        "source_label_totals": source_totals,
        "filter_errors": filter_errors,
        "pages_scanned": pages_scanned,
        "dataset_rows_reported": total_rows,
    }


async def sync_external_benchmark(db, per_class: int = 250) -> Dict[str, Any]:
    """Import a bounded class-balanced independent corpus."""
    await ensure_external_benchmark_schema(db)
    per_class = max(1, min(MAX_PER_CLASS, int(per_class)))
    buckets, fetch_meta = await _fetch_balanced_rows(per_class)
    rows = buckets[0][:per_class] + buckets[1][:per_class]
    refreshed = 0
    for row in rows:
        result = await db.execute(
            """
            INSERT INTO external_detection_benchmark_cases (
                source, source_row_idx, tx_hash, label, from_address, to_address,
                value_wei_text, gas, gas_price_text, block_timestamp_text,
                block_number, category, source_reference
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            ON CONFLICT (source, source_row_idx) DO UPDATE SET
                tx_hash=EXCLUDED.tx_hash,label=EXCLUDED.label,from_address=EXCLUDED.from_address,
                to_address=EXCLUDED.to_address,value_wei_text=EXCLUDED.value_wei_text,
                gas=EXCLUDED.gas,gas_price_text=EXCLUDED.gas_price_text,
                block_timestamp_text=EXCLUDED.block_timestamp_text,block_number=EXCLUDED.block_number,
                category=EXCLUDED.category,source_reference=EXCLUDED.source_reference,imported_at=NOW()
            """,
            SOURCE_NAME,row["source_row_idx"],row["tx_hash"],row["label"],row["from_address"],row["to_address"],
            row["value_wei_text"],row["gas"],row["gas_price_text"],row["block_timestamp_text"],row["block_number"],row["category"],SOURCE_REFERENCE,
        )
        if result:
            refreshed += 1
    logger.info(
        "External benchmark sync refreshed {} rows from {} using {} ({} negatives, {} positives)",
        refreshed,SOURCE_NAME,fetch_meta.get("mode"),len(buckets[0]),len(buckets[1]),
    )
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