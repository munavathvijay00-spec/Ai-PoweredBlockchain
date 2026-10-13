"""Evaluate binary review flags against manually labeled cases.

Input CSV columns: case_id, actual_label, predicted_flag
Labels must be 0 or 1. This tool does not generate labels or infer fraud.
Run: python scripts/evaluate_detection.py labeled_cases.csv
"""
import csv
import json
import sys
from pathlib import Path


def evaluate(rows):
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    seen = set()
    for row in rows:
        case_id = str(row["case_id"]).strip()
        if not case_id or case_id in seen:
            raise ValueError("case_id must be nonempty and unique")
        seen.add(case_id)
        actual = str(row["actual_label"]).strip()
        predicted = str(row["predicted_flag"]).strip()
        if actual not in {"0", "1"} or predicted not in {"0", "1"}:
            raise ValueError(f"Invalid binary label in case {case_id}")
        a, p = int(actual), int(predicted)
        counts[("tp" if a else "fp") if p else ("fn" if a else "tn")] += 1
    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    def ratio(num, den):
        return num / den if den else None
    return {
        "cases": len(seen),
        "confusion_matrix": counts,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + tn, len(seen)),
        "false_positive_rate": ratio(fp, fp + tn),
        "false_negative_rate": ratio(fn, fn + tp),
        "positive_support": tp + fn,
        "negative_support": tn + fp,
        "note": "Unmeasured metrics are null. Validity depends on independent ground-truth labels and representative sampling.",
    }


def main(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"case_id", "actual_label", "predicted_flag"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Required CSV columns: case_id, actual_label, predicted_flag")
        result = evaluate(reader)
    if result["cases"] == 0:
        raise ValueError("No labeled cases supplied")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/evaluate_detection.py labeled_cases.csv")
    try:
        main(sys.argv[1])
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
