"""Join blind human labels with sealed detector predictions and evaluate them.

The files stay separate until evaluation time to prevent label leakage.

Usage:
    python scripts/evaluate_blind_holdout.py labels.csv predictions.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts.evaluate_detection import evaluate


def _read_unique(path: str, required: set[str]) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = required.difference(reader.fieldnames or [])
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                raise ValueError(f"Blank case_id in {path}")
            if case_id in rows:
                raise ValueError(f"Duplicate case_id {case_id} in {path}")
            rows[case_id] = row
        return rows


def join_rows(labels_path: str, predictions_path: str) -> list[dict[str, str]]:
    labels = _read_unique(labels_path, {"case_id", "actual_label"})
    predictions = _read_unique(predictions_path, {"case_id", "predicted_flag"})

    if set(labels) != set(predictions):
        only_labels = sorted(set(labels).difference(predictions))[:10]
        only_predictions = sorted(set(predictions).difference(labels))[:10]
        raise ValueError(
            "Label/prediction case mismatch; "
            f"labels_only={only_labels}, predictions_only={only_predictions}"
        )

    joined = []
    for case_id in sorted(labels):
        label = str(labels[case_id].get("actual_label") or "").strip()
        if label not in {"0", "1"}:
            raise ValueError(f"Case {case_id} is not independently adjudicated with 0 or 1")
        joined.append({
            "case_id": case_id,
            "actual_label": label,
            "predicted_flag": str(predictions[case_id].get("predicted_flag") or "").strip(),
        })
    return joined


def main(labels_path: str, predictions_path: str) -> None:
    joined = join_rows(labels_path, predictions_path)
    if not joined:
        raise ValueError("No cases supplied")
    result = evaluate(joined)
    result["evaluation_protocol"] = {
        "name": "blind_independent_holdout",
        "labels_path": labels_path,
        "predictions_path": predictions_path,
        "labeler_prediction_visibility_required": False,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/evaluate_blind_holdout.py labels.csv predictions.csv")
    try:
        main(sys.argv[1], sys.argv[2])
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
