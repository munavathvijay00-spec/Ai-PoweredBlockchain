"""Independently supervised transaction-risk model.

This module deliberately does NOT learn from ChainScope risk_score or detector outputs.
Training labels come from `external_detection_benchmark_cases`, which is populated from
an external labelled dataset. The model is calibrated on a validation partition and is
only eligible for production *shadow* inference when provenance and evaluation metadata
pass explicit quality gates.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import joblib
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.database.connection import get_db

MODEL_PATH = Path("models/independent_risk_model.pkl")
METADATA_PATH = Path("models/independent_risk_model.metadata.json")
FEATURE_COLUMNS = (
    "value_log_eth",
    "gas_log",
    "gas_price_log_gwei",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
)
SOURCE_PREFIX = "huggingface:"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _timestamp_parts(value: Any) -> tuple[int, int]:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return 0, 0
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0, 0
    return int(dt.hour), int(dt.weekday())


def build_features(row: Dict[str, Any]) -> Dict[str, float]:
    """Features available both in the independent dataset and live Ethereum transfers.

    No ChainScope risk score, blacklist flag, detector output, entity attribution, or
    post-label intelligence feature is permitted here; that prevents target leakage.
    """
    raw_value = row.get("value_wei_text", row.get("value", 0))
    raw_gas_price = row.get("gas_price_text", row.get("gas_price", 0))
    value_eth = max(0.0, _safe_float(raw_value) / 1e18)
    gas = max(0.0, _safe_float(row.get("gas", row.get("gas_used", 0))))
    gas_price_gwei = max(0.0, _safe_float(raw_gas_price) / 1e9)
    hour, weekday = _timestamp_parts(row.get("block_timestamp_text", row.get("timestamp")))
    return {
        "value_log_eth": float(np.log1p(value_eth)),
        "gas_log": float(np.log1p(gas)),
        "gas_price_log_gwei": float(np.log1p(gas_price_gwei)),
        "hour_sin": math.sin(2 * math.pi * hour / 24.0),
        "hour_cos": math.cos(2 * math.pi * hour / 24.0),
        "weekday_sin": math.sin(2 * math.pi * weekday / 7.0),
        "weekday_cos": math.cos(2 * math.pi * weekday / 7.0),
    }


def _vector(row: Dict[str, Any]) -> list[float]:
    f = build_features(row)
    return [f[name] for name in FEATURE_COLUMNS]


def _partition(tx_hash: str) -> str:
    """Stable hash split prevents accidental train/test reshuffling between runs."""
    bucket = int(hashlib.sha256(tx_hash.lower().encode()).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _metrics(y_true: np.ndarray, probability: np.ndarray, threshold: float) -> Dict[str, float]:
    pred = (probability >= threshold).astype(int)
    result = {
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "brier": float(brier_score_loss(y_true, probability)),
    }
    result["roc_auc"] = float(roc_auc_score(y_true, probability)) if len(set(y_true.tolist())) == 2 else 0.0
    return result


def _best_threshold(y_true: np.ndarray, probability: np.ndarray) -> float:
    best = (0.5, -1.0)
    for threshold in np.linspace(0.10, 0.90, 81):
        score = f1_score(y_true, probability >= threshold, zero_division=0)
        if score > best[1]:
            best = (float(threshold), float(score))
    return best[0]


def _dataset_fingerprint(rows: Iterable[Dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda x: str(x["tx_hash"])):
        digest.update(f"{row['tx_hash']}|{int(row['label'])}|{row['source']}\n".encode())
    return digest.hexdigest()


async def _load_external_rows(limit: int = 5000) -> list[Dict[str, Any]]:
    db = await get_db()
    rows = await db.fetch(
        """
        SELECT source, source_row_idx, tx_hash, label, from_address, to_address,
               value_wei_text, gas, gas_price_text, block_timestamp_text, block_number,
               category, source_reference
        FROM external_detection_benchmark_cases
        ORDER BY source, source_row_idx
        LIMIT $1
        """,
        max(100, min(50000, int(limit))),
    )
    return [dict(row) for row in rows]


async def train_independent_model(limit: int = 5000) -> Dict[str, Any]:
    rows = await _load_external_rows(limit)
    if len(rows) < 100:
        raise ValueError(f"Need at least 100 independently labelled cases; found {len(rows)}")
    if any(not str(row.get("source") or "").startswith(SOURCE_PREFIX) for row in rows):
        raise ValueError("Refusing training: dataset contains a non-independent label source")
    labels = [int(row["label"]) for row in rows]
    if min(labels.count(0), labels.count(1)) < 30:
        raise ValueError("Need at least 30 independently labelled examples in each class")

    groups: Dict[str, list[Dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row in rows:
        groups[_partition(str(row["tx_hash"]))].append(row)
    for name, items in groups.items():
        classes = {int(item["label"]) for item in items}
        if len(items) < 10 or classes != {0, 1}:
            raise ValueError(f"{name} partition is too small or lacks both classes: {len(items)} rows")

    def matrix(items):
        return np.asarray([_vector(row) for row in items], dtype=float), np.asarray([int(row["label"]) for row in items], dtype=int)

    X_train, y_train = matrix(groups["train"])
    X_val, y_val = matrix(groups["validation"])
    X_test, y_test = matrix(groups["test"])

    positives = max(1, int((y_train == 1).sum()))
    negatives = max(1, int((y_train == 0).sum()))
    model = xgb.XGBClassifier(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.04,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=2.0,
        min_child_weight=2,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=negatives / positives,
        random_state=42,
        n_jobs=2,
    )
    model.fit(X_train, y_train)

    # Platt calibration is fit ONLY on validation predictions; test remains untouched.
    val_raw = model.predict_proba(X_val)[:, 1]
    calibrator = LogisticRegression(random_state=42)
    calibrator.fit(val_raw.reshape(-1, 1), y_val)
    val_prob = calibrator.predict_proba(val_raw.reshape(-1, 1))[:, 1]
    threshold = _best_threshold(y_val, val_prob)

    test_raw = model.predict_proba(X_test)[:, 1]
    test_prob = calibrator.predict_proba(test_raw.reshape(-1, 1))[:, 1]
    test_metrics = _metrics(y_test, test_prob, threshold)
    val_metrics = _metrics(y_val, val_prob, threshold)

    # With the current 100-case benchmark this is a research/shadow model. Promotion
    # requires a materially larger independent corpus and minimum discrimination.
    sample_tier = "production_candidate" if len(rows) >= 500 else "research_shadow"
    quality_pass = bool(
        sample_tier == "production_candidate"
        and test_metrics["roc_auc"] >= 0.70
        and test_metrics["f1"] >= 0.60
    )
    metadata = {
        "schema_version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "supervision": "independent_external_labels",
        "label_source_prefix": SOURCE_PREFIX,
        "dataset_rows": len(rows),
        "dataset_fingerprint_sha256": _dataset_fingerprint(rows),
        "split_strategy": "sha256(tx_hash):70/15/15",
        "split_sizes": {name: len(items) for name, items in groups.items()},
        "features": list(FEATURE_COLUMNS),
        "calibration": "platt_logistic_on_validation_only",
        "threshold": threshold,
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "sample_tier": sample_tier,
        "production_quality_gate_passed": quality_pass,
        "deployment_mode": "shadow" if not quality_pass else "eligible_for_review",
        "limitations": [
            "External benchmark may not represent current Ethereum traffic.",
            "Model probability is a calibrated classification score, not probability of criminality.",
            "No ChainScope heuristic risk score or detector output is used as a training feature or label.",
        ],
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "calibrator": calibrator, "metadata": metadata}, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2, sort_keys=True))
    return metadata


def load_independent_bundle() -> Dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(str(MODEL_PATH))
    bundle = joblib.load(MODEL_PATH)
    if not isinstance(bundle, dict) or "model" not in bundle or "calibrator" not in bundle or "metadata" not in bundle:
        raise ValueError("Invalid independent model bundle")
    metadata = bundle["metadata"]
    if metadata.get("supervision") != "independent_external_labels":
        raise ValueError("Model provenance gate failed")
    if tuple(metadata.get("features") or ()) != FEATURE_COLUMNS:
        raise ValueError("Model feature schema mismatch")
    return bundle


def predict_independent(row: Dict[str, Any]) -> Dict[str, Any]:
    bundle = load_independent_bundle()
    raw = float(bundle["model"].predict_proba(np.asarray([_vector(row)], dtype=float))[0, 1])
    probability = float(bundle["calibrator"].predict_proba(np.asarray([[raw]], dtype=float))[0, 1])
    metadata = bundle["metadata"]
    threshold = float(metadata["threshold"])
    return {
        "label": int(probability >= threshold),
        "probability": probability,
        "threshold": threshold,
        "mode": metadata.get("deployment_mode", "shadow"),
        "sample_tier": metadata.get("sample_tier"),
        "dataset_fingerprint_sha256": metadata.get("dataset_fingerprint_sha256"),
        "production_quality_gate_passed": bool(metadata.get("production_quality_gate_passed")),
    }


def model_status() -> Dict[str, Any]:
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        return {"available": False, "mode": "not_trained", "production_quality_gate_passed": False}
    try:
        metadata = json.loads(METADATA_PATH.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        return {"available": False, "mode": "metadata_invalid", "production_quality_gate_passed": False}
    return {
        "available": True,
        "mode": metadata.get("deployment_mode"),
        "supervision": metadata.get("supervision"),
        "dataset_rows": metadata.get("dataset_rows"),
        "sample_tier": metadata.get("sample_tier"),
        "production_quality_gate_passed": bool(metadata.get("production_quality_gate_passed")),
        "test_metrics": metadata.get("test_metrics"),
        "trained_at": metadata.get("trained_at"),
        "dataset_fingerprint_sha256": metadata.get("dataset_fingerprint_sha256"),
    }
