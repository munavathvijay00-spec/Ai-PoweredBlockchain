"""Independently supervised transaction-risk model.

Training labels come only from external labelled data. ChainScope risk scores, detector
outputs, entity intelligence, blacklist state, and AI output are prohibited from both
labels and features.

Evaluation isolates address-connected components across train/validation/test. A model
may pass the internal benchmark quality gate, but production promotion additionally
requires label-source diversity. A single-source benchmark remains a shadow signal even
when its measured holdout metrics are excellent.
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
MODEL_SCHEMA_VERSION = 4
SPLIT_STRATEGY = "address_connected_components_sha256_70_15_15"
SOURCE_PREFIX = "huggingface:"
MIN_PRODUCTION_LABEL_SOURCES = 2
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
    """Build only features available independently of ChainScope's risk engine."""
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
        small, large = sorted((ra, rb))
        parent[large] = small

    row_nodes: list[list[str]] = []
    for row in rows:
        nodes = [
            node for node in (
                _valid_address(row.get("from_address")),
                _valid_address(row.get("to_address")),
            ) if node
        ]
        if not nodes:
            nodes = [f"tx:{str(row['tx_hash']).lower()}"]
        for node in nodes:
            find(node)
        for node in nodes[1:]:
            union(nodes[0], node)
        row_nodes.append(nodes)

    members: Dict[str, list[str]] = {}
    for node in list(parent):
        members.setdefault(find(node), []).append(node)
    canonical = {root: min(nodes) for root, nodes in members.items()}

    groups: Dict[str, list[Dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row, nodes in zip(rows, row_nodes):
        groups[_bucket(canonical[find(nodes[0])])].append(row)
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

    label_sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
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
    benchmark_quality_pass = bool(
        sample_tier == "production_candidate"
        and not any(overlaps.values())
        and test_metrics["roc_auc"] >= 0.70
        and test_metrics["f1"] >= 0.60
    )
    source_diversity_pass = len(label_sources) >= MIN_PRODUCTION_LABEL_SOURCES
    production_quality_pass = bool(benchmark_quality_pass and source_diversity_pass)

    if production_quality_pass:
        deployment_mode = "eligible_for_production_review"
    elif benchmark_quality_pass:
        deployment_mode = "shadow_single_source"
    else:
        deployment_mode = "shadow"

    metadata = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "supervision": "independent_external_labels",
        "label_source_prefix": SOURCE_PREFIX,
        "label_sources": label_sources,
        "label_source_count": len(label_sources),
        "minimum_production_label_sources": MIN_PRODUCTION_LABEL_SOURCES,
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
        "benchmark_quality_gate_passed": benchmark_quality_pass,
        "source_diversity_gate_passed": source_diversity_pass,
        "production_quality_gate_passed": production_quality_pass,
        "deployment_mode": deployment_mode,
        "promotion_blockers": [] if production_quality_pass else [
            reason for condition, reason in (
                (benchmark_quality_pass, "benchmark_quality_gate_not_passed"),
                (source_diversity_pass, "requires_independent_second_label_source"),
            ) if not condition
        ],
        "limitations": [
            "External benchmark is balanced and is not a prevalence estimate for current Ethereum traffic.",
            "Current benchmark source diversity is explicitly tracked; a single-source model cannot be promoted into production scoring.",
            "Model score is a calibrated classification score, not probability of criminality.",
            "No ChainScope heuristic risk score, detector output, entity label, blacklist state, or AI output is used as a feature or label.",
            "Address-connected components are isolated across train/validation/test to reduce related-wallet leakage.",
            "Production rule scoring remains unchanged unless a separately reviewed promotion gate is satisfied.",
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
        "benchmark_quality_gate_passed": bool(metadata.get("benchmark_quality_gate_passed")),
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
        "label_source_count": metadata.get("label_source_count"),
        "dataset_rows": metadata.get("dataset_rows"),
        "sample_tier": metadata.get("sample_tier"),
        "split_strategy": metadata.get("split_strategy"),
        "address_overlap_counts": metadata.get("address_overlap_counts"),
        "benchmark_quality_gate_passed": bool(metadata.get("benchmark_quality_gate_passed")),
        "source_diversity_gate_passed": bool(metadata.get("source_diversity_gate_passed")),
        "production_quality_gate_passed": bool(metadata.get("production_quality_gate_passed")),
        "promotion_blockers": metadata.get("promotion_blockers") or [],
        "test_metrics": metadata.get("test_metrics"),
        "trained_at": metadata.get("trained_at"),
        "dataset_fingerprint_sha256": metadata.get("dataset_fingerprint_sha256"),
    }
