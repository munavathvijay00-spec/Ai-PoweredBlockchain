"""Unsupervised behavioral anomaly signal for retained Ethereum transactions.

This model is deliberately separate from fraud classification. It learns the shape of
recent retained Ethereum activity and reports how unusual a transaction looks relative
to that retained sample. It never labels criminality and abstains when the sample is too
small.
"""
from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

MIN_SAMPLE_SIZE = 100
MAX_SAMPLE_SIZE = 3000
MODEL_NAME = "retained_behavior_isolation_forest"
MODEL_VERSION = 1


def _safe_float(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _timestamp_parts(value: Any) -> tuple[int, int]:
    if value is None:
        return 0, 0
    try:
        return int(value.hour), int(value.weekday())
    except Exception:
        return 0, 0


def _feature_vector(row: Dict[str, Any]) -> list[float]:
    value_eth = max(0.0, _safe_float(row.get("value")) / 1e18)
    gas_used = max(0.0, _safe_float(row.get("gas_used")))
    gas_price_gwei = max(0.0, _safe_float(row.get("gas_price")) / 1e9)
    hour, weekday = _timestamp_parts(row.get("timestamp"))
    sender_count = max(0.0, _safe_float(row.get("sender_tx_count")))
    recipient_count = max(0.0, _safe_float(row.get("recipient_tx_count")))
    sender_counterparties = max(0.0, _safe_float(row.get("sender_unique_counterparties")))
    recipient_counterparties = max(0.0, _safe_float(row.get("recipient_unique_counterparties")))
    return [
        math.log1p(value_eth),
        math.log1p(gas_used),
        math.log1p(gas_price_gwei),
        math.sin(2 * math.pi * hour / 24.0),
        math.cos(2 * math.pi * hour / 24.0),
        math.sin(2 * math.pi * weekday / 7.0),
        math.cos(2 * math.pi * weekday / 7.0),
        math.log1p(sender_count),
        math.log1p(recipient_count),
        math.log1p(sender_counterparties),
        math.log1p(recipient_counterparties),
    ]


async def _retained_feature_rows(db, limit: int = MAX_SAMPLE_SIZE) -> list[Dict[str, Any]]:
    rows = await db.fetch(
        """
        WITH sender_stats AS (
            SELECT from_address_id AS address_id,
                   COUNT(*) AS tx_count,
                   COUNT(DISTINCT to_address_id) AS unique_counterparties
            FROM transactions
            GROUP BY from_address_id
        ), recipient_stats AS (
            SELECT to_address_id AS address_id,
                   COUNT(*) AS tx_count,
                   COUNT(DISTINCT from_address_id) AS unique_counterparties
            FROM transactions
            GROUP BY to_address_id
        )
        SELECT t.hash, t.value, t.gas_used, t.gas_price, t.timestamp,
               COALESCE(ss.tx_count, 0) AS sender_tx_count,
               COALESCE(rs.tx_count, 0) AS recipient_tx_count,
               COALESCE(ss.unique_counterparties, 0) AS sender_unique_counterparties,
               COALESCE(rs.unique_counterparties, 0) AS recipient_unique_counterparties
        FROM transactions t
        LEFT JOIN sender_stats ss ON ss.address_id=t.from_address_id
        LEFT JOIN recipient_stats rs ON rs.address_id=t.to_address_id
        ORDER BY t.block_number DESC, t.id DESC
        LIMIT $1
        """,
        max(MIN_SAMPLE_SIZE, min(MAX_SAMPLE_SIZE, int(limit))),
    )
    return [dict(row) for row in rows]


async def transaction_anomaly(db, tx_hash: str, limit: int = MAX_SAMPLE_SIZE) -> Dict[str, Any]:
    """Return a retained-sample anomaly percentile, or explicitly abstain."""
    rows = await _retained_feature_rows(db, limit=limit)
    if len(rows) < MIN_SAMPLE_SIZE:
        return {
            "available": False,
            "status": "insufficient_sample",
            "sample_size": len(rows),
            "minimum_sample_size": MIN_SAMPLE_SIZE,
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "interpretation": "No anomaly claim is produced because the retained comparison sample is too small.",
        }

    index = next((i for i, row in enumerate(rows) if str(row.get("hash") or "").lower() == tx_hash.lower()), None)
    if index is None:
        return {
            "available": False,
            "status": "transaction_not_in_retained_sample",
            "sample_size": len(rows),
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "interpretation": "The transaction is outside the retained sample; no anomaly score was inferred.",
        }

    matrix = np.asarray([_feature_vector(row) for row in rows], dtype=float)
    scaler = RobustScaler()
    scaled = scaler.fit_transform(matrix)
    model = IsolationForest(
        n_estimators=160,
        max_samples=min(512, len(rows)),
        contamination="auto",
        random_state=42,
        n_jobs=1,
    )
    model.fit(scaled)
    raw_scores = -model.score_samples(scaled)  # larger => more unusual
    target_score = float(raw_scores[index])
    percentile = float(np.mean(raw_scores <= target_score))
    band = "high" if percentile >= 0.95 else "elevated" if percentile >= 0.80 else "typical"
    return {
        "available": True,
        "status": "scored",
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "sample_size": len(rows),
        "anomaly_percentile": round(percentile, 6),
        "anomaly_band": band,
        "raw_anomaly_score": round(target_score, 6),
        "features": [
            "value_eth_log", "gas_used_log", "gas_price_gwei_log",
            "hour_cyclical", "weekday_cyclical", "sender_activity",
            "recipient_activity", "sender_counterparty_diversity",
            "recipient_counterparty_diversity",
        ],
        "scope": "Relative only to ChainScope's currently retained recent Ethereum sample.",
        "interpretation": "Behavioral anomaly signal only. Unusual activity is not evidence of fraud, criminality, sanctions exposure, or malicious intent.",
    }
