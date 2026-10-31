"""Reproducible *exploratory* baseline on external labelled transactions.

Usage (in an environment with configured DATABASE_URL and application settings):
    python -m scripts.evaluate_rule_baseline

This experiment does not estimate deployed fraud accuracy. The external benchmark
is balanced, sampled, and lacks historical/entity context. Never tune production
thresholds on this report or call this an independently held-out production test.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix, precision_score, recall_score, f1_score,
    balanced_accuracy_score, roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit

from src.database.connection import get_db, close_db
from src.risk.external_benchmark import SOURCE_NAME, ensure_external_benchmark_schema


def extract_features(row):
    """Features available in the external dataset, without label-derived signals."""
    def nonnegative_number(value):
        try:
            return max(0.0, float(value or 0))
        except (ValueError, TypeError, OverflowError):
            return 0.0

    value = nonnegative_number(row["value_wei_text"])
    gas = nonnegative_number(row["gas"])
    gas_price = nonnegative_number(row["gas_price_text"])
    return [np.log1p(value), np.log1p(gas), np.log1p(gas_price)]


def metrics(y_true, y_pred, probabilities=None):
    tn, fp, fn, tp = (int(x) for x in confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel())
    result = {
        "true_negative": tn, "false_positive": fp,
        "false_negative": fn, "true_positive": tp,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else None,
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
    }
    if probabilities is not None and len(set(y_true)) == 2:
        result["roc_auc"] = float(roc_auc_score(y_true, probabilities))
    return result


async def evaluate():
    db = await get_db()
    try:
        await ensure_external_benchmark_schema(db)
        rows = await db.fetch(
            """SELECT source_row_idx,tx_hash,label,from_address,to_address,
                      value_wei_text,gas,gas_price_text
               FROM external_detection_benchmark_cases
               WHERE source=$1 ORDER BY source_row_idx""", SOURCE_NAME,
        )
        if len(rows) < 100:
            raise RuntimeError("At least 100 externally labelled cases are required")
        features = np.array([extract_features(row) for row in rows], dtype=float)
        labels = np.array([int(row["label"]) for row in rows])
        # Prevent sender overlap where possible; null senders grouped by
        # transaction hash so unknown addresses never create a giant group.
        groups = [
            (row["from_address"] or row["tx_hash"]).lower()
            for row in rows
        ]
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
        train, test = next(splitter.split(features, labels, groups))
        if len(set(labels[train])) != 2 or len(set(labels[test])) != 2:
            raise RuntimeError("Grouped holdout lacks both classes; no valid comparison")
        baseline = DummyClassifier(strategy="most_frequent")
        baseline.fit(features[train], labels[train])
        lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
        lr.fit(features[train], labels[train])
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": SOURCE_NAME,
            "rows_total": len(rows),
            "rows_train": len(train),
            "rows_holdout": len(test),
            "split": "grouped_by_from_address_when_available",
            "random_seed": 42,
            "feature_names": ["log1p(value_wei)", "log1p(gas)", "log1p(gas_price_wei)"],
            "majority_class_baseline": metrics(labels[test], baseline.predict(features[test])),
            "logistic_regression": metrics(
                labels[test], lr.predict(features[test]),
                lr.predict_proba(features[test])[:, 1],
            ),
            "limitations": [
                "Balanced curated dataset is not representative of live Ethereum fraud prevalence.",
                "Feature fields omit address history, verified entity matches and graph context.",
                "Grouped holdout prevents exact source-address overlap but not all actor or temporal leakage.",
                "This is exploratory ML comparison only, not ChainScope deployment accuracy.",
                "No calibrated fraud probability or automated production threshold change is claimed.",
            ],
        }
        print(json.dumps(report, indent=2, allow_nan=False))
        return report
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(evaluate())
