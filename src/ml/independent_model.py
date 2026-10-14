"""Independently supervised transaction-risk model.

Training labels come only from an external labelled dataset. ChainScope risk scores,
detector outputs, entity intelligence, blacklist state, and AI output are prohibited from
both labels and features.

Evaluation uses address-connected-component isolation: if two benchmark transactions
share an endpoint directly or transitively, they are assigned to the same partition.
This prevents related-wallet activity from leaking between train, validation, and test.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score

from src.database.connection import get_db

MODEL_PATH = Path("models/independent_risk_model.pkl")
METADATA_PATH = Path("models/independent_risk_model.metadata.json")
MODEL_FAMILY = "sklearn_hist_gradient_boosting"
MODEL_SCHEMA_VERSION = 3
SPLIT_STRATEGY = "address_connected_components_sha256_70_15_15"
SOURCE_PREFIX = "huggingface:"
FEATURE_COLUMNS = (
    "value_log_eth",
    "gas_log",
    "gas_price_log_gwei",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
)


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
    features = build_features(row)
    return [features[name] for name in FEATURE_COLUMNS]


def _bucket(key: str) -> str:
    value = int(hashlib.sha256(key.lower().encode()).hexdigest()[:8], 16) % 100
    if value < 70:
        return "train"
    if value < 85:
        return "validation"
    return "test"


def _valid_address(value: Any) -> str | None:
    text = str(value or "").lower()
    return text if len(text) == 42 and text.startswith("0x") else None


def _partition_rows(rows: list[Dict[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    """Keep every address-connected component entirely inside one partition."""
    parent: Dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Lexical root selection makes component IDs deterministic across row order.
        small, large = sorted((ra, rb))
        parent[large] = small

    row_nodes: list[list[str]] = []
    for row in rows:
        nodes = [node for node in (_valid_address(row.get("from_address")), _valid_address(row.get("to_address"))) if node]
        if not nodes:
            nodes = [f"tx:{str(row['tx_hash']).lower()}"]
        for node in nodes:
            find(node)
        for node in nodes[1:]:
            union(nodes[0], node)
        row_nodes.append(nodes)

    # Compress after all unions, then use the lexically smallest member as component key.
    members: Dict[str, list[str]] = {}
    for node in list(parent):
        members.setdefault(find(node), []).append(node)
    canonical = {root: min(nodes) for root, nodes in members.items()}

    groups: Dict[str, list[Dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row, nodes in zip(rows, row_nodes):
        component_key = canonical[find(nodes[0])]
        groups[_bucket(component_key)].append(row)
    return groups


def _partition_address_sets(groups: Dict[str, list[Dict[str, Any]]]) -> Dict[str, set[str]]:
    result: Dict[str, set[str]] = {}
    for name, rows in groups.items():
        addresses = set()
        for row in rows:
            for value in (row.get("from_address"), row.get("to_address")):
                address = _valid_address(value)
                if address:
                    addresses.add(address)
        result[name] = addresses
    return result


def _address_overlap(groups: Dict[str, list[Dict[str, Any]]]) -> Dict[str, int]:
    sets = _partition_address_sets(groups)
    return {
        "train_validation": len(sets["train"] & sets["validation"]),
        "train_test": len(sets["train"] & sets["test"]),
        "validation_test": len(sets["validation"] & sets["test"]),
    }


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
    best_threshold, best_score = 0.5, -1.0
    for threshold in np.linspace(0.10, 0.90, 81):
        score = f1_score(y_true, probability >= threshold, zero_division=0)
        if score > best_score:
            best_threshold, best_score = float(threshold), float(score)
    return best_threshold


def _dataset_fingerprint(rows: Iterable[Dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["tx_hash"])):
        digest.update(f"{row['tx_hash']}|{int(row['label'])}|{row['source']}\n".encode())
    return digest.hexdigest()


def _balanced_sample_weight(labels: np.ndarray) -> np.ndarray:
    counts = np.bincount(labels, minlength=2).astype(float)
    total = float(len(labels))
    weights = np.ones(len(labels), dtype=float)
    for label in (0, 1):
        if counts[label] > 0:
            weights[labels == label] = total / (2.0 * counts[label])
    return weights


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

    groups = _partition_rows(rows)
    overlaps = _address_overlap(groups)
    if any(overlaps.values()):
        raise ValueError(f"Address leakage detected across partitions: {overlaps}")
    for name, items in groups.items():
        classes = {int(item["label"]) for item in items}
        if len(items) < 20 or classes != {0, 1}:
            raise ValueError(f"{name} wallet-isolated partition is too small or lacks both classes: {len(items)} rows")

    def matrix(items):
        return (
            np.asarray([_vector(row) for row in items], dtype=float),
            np.asarray([int(row["label"]) for row in items], dtype=int),
        )

    X_train, y_train = matrix(groups["train"])
    X_val, y_val = matrix(groups["validation"])
    X_test, y_test = matrix(groups["test"])

    model = HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=180,
        max_leaf_nodes=15,
        max_depth=4,
        min_samples_leaf=max(8, min(20, len(X_train) // 20)),
        l2_regularization=1.5,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=20,
        random_state=42,
    )
    model.fit(X_train, y_train, sample_weight=_balanced_sample_weight(y_train))

    val_raw = model.predict_proba(X_val)[:, 1]
    calibrator = LogisticRegression(random_state=42)
    calibrator.fit(val_raw.reshape(-1, 1), y_val)
    val_prob = calibrator.predict_proba(val_raw.reshape(-1, 1))[:, 1]
    threshold = _best_threshold(y_val, val_prob)

    test_raw = model.predict_proba(X_test)[:, 1]
    test_prob = calibrator.predict_proba(test_raw.reshape(-1, 1))[:, 1]
    test_metrics = _metrics(y_test, test_prob, threshold)
    val_metrics = _metrics(y_val, val_prob, threshold)

    sample_tier = "production_candidate" if len(rows) >= 500 else "research_shadow"
    quality_pass = bool(
        sample_tier == "production_candidate"
        and not any(overlaps.values())
        and test_metrics["roc_auc"] >= 0.70
        and test_metrics["f1"] >= 0.60
    )
    metadata = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "supervision": "independent_external_labels",
        "label_source_prefix": SOURCE_PREFIX,
        "dataset_rows": len(rows),
        "dataset_fingerprint_sha256": _dataset_fingerprint(rows),
        "split_strategy": SPLIT_STRATEGY,
        "split_sizes": {name: len(items) for name, items in groups.items()},
        "address_overlap_counts": overlaps,
        "features": list(FEATURE_COLUMNS),
        "calibration": "platt_logistic_on_validation_only",
        "threshold": threshold,
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "sample_tier": sample_tier,
        "production_quality_gate_passed": quality_pass,
        "deployment_mode": "shadow" if not quality_pass else "eligible_for_review",
        "limitations": [
            "External benchmark is a balanced single-source sample and is not current Ethereum prevalence.",
            "Model score is a calibrated classification score, not probability of criminality.",
            "No ChainScope heuristic risk score, detector output, entity label, blacklist state, or AI output is used as a feature or label.",
            "Address-connected components are isolated across train/validation/test to reduce related-wallet leakage.",
            "Passing this quality gate does not automatically alter the production rule score.",
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
    if metadata.get("model_family") != MODEL_FAMILY or int(metadata.get("schema_version") or 0) != MODEL_SCHEMA_VERSION:
        raise ValueError("Model runtime schema mismatch")
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
        "model_family": metadata.get("model_family"),
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
        "model_family": metadata.get("model_family"),
        "schema_version": metadata.get("schema_version"),
        "supervision": metadata.get("supervision"),
        "dataset_rows": metadata.get("dataset_rows"),
        "sample_tier": metadata.get("sample_tier"),
        "split_strategy": metadata.get("split_strategy"),
        "address_overlap_counts": metadata.get("address_overlap_counts"),
        "production_quality_gate_passed": bool(metadata.get("production_quality_gate_passed")),
        "test_metrics": metadata.get("test_metrics"),
        "trained_at": metadata.get("trained_at"),
        "dataset_fingerprint_sha256": metadata.get("dataset_fingerprint_sha256"),
    }
