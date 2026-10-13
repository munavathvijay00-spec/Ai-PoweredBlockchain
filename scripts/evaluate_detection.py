"""Evaluate detector decisions against independently labeled cases.

Input CSV columns: case_id, actual_label, predicted_flag
- actual_label: 0 or 1 from an independent adjudication process.
- predicted_flag: 0, 1, or abstain.

Abstentions are kept explicit. A positive abstention counts as an operational
miss for alerting recall, but abstentions are never silently converted to a
benign prediction.

Run: python scripts/evaluate_detection.py labeled_cases.csv
"""
import csv
import json
import math
import sys
from pathlib import Path


def _ratio(num, den):
    return num / den if den else None


def _wilson(successes, total, z=1.959963984540054):
    """95% Wilson score interval for a binomial proportion."""
    if not total:
        return None
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
        / denominator
    )
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def _normalize_prediction(value):
    text = str(value).strip().lower()
    aliases = {
        "0": "0",
        "clear": "0",
        "negative": "0",
        "1": "1",
        "flag": "1",
        "flagged": "1",
        "review": "1",
        "abstain": "abstain",
        "unknown": "abstain",
        "insufficient_evidence": "abstain",
    }
    if text not in aliases:
        raise ValueError("predicted_flag must be 0, 1, or abstain")
    return aliases[text]


def evaluate(rows):
    counts = {
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 0,
        "abstain_positive": 0,
        "abstain_negative": 0,
    }
    seen = set()

    for row in rows:
        case_id = str(row["case_id"]).strip()
        if not case_id or case_id in seen:
            raise ValueError("case_id must be nonempty and unique")
        seen.add(case_id)

        actual = str(row["actual_label"]).strip()
        if actual not in {"0", "1"}:
            raise ValueError(f"Invalid actual_label in case {case_id}; expected 0 or 1")
        prediction = _normalize_prediction(row["predicted_flag"])
        label = int(actual)

        if prediction == "abstain":
            counts["abstain_positive" if label else "abstain_negative"] += 1
        elif prediction == "1":
            counts["tp" if label else "fp"] += 1
        else:
            counts["fn" if label else "tn"] += 1

    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    abstain_positive = counts["abstain_positive"]
    abstain_negative = counts["abstain_negative"]
    total = len(seen)
    decided = tp + fp + tn + fn
    positive_support = tp + fn + abstain_positive
    negative_support = tn + fp + abstain_negative
    predicted_positive = tp + fp
    decided_positive_labels = tp + fn
    decided_negative_labels = tn + fp

    # For an alerting system, abstaining on a positive case is operationally a
    # missed alert. Negative abstentions remain abstentions, not true negatives.
    operational_fn = fn + abstain_positive
    precision = _ratio(tp, predicted_positive)
    recall = _ratio(tp, positive_support)
    f1 = _ratio(2 * tp, 2 * tp + fp + operational_fn)

    result = {
        "cases": total,
        "decided_cases": decided,
        "abstentions": abstain_positive + abstain_negative,
        "confusion_matrix": counts,
        "precision": precision,
        "recall": recall,
        "specificity": _ratio(tn, decided_negative_labels),
        "f1": f1,
        "accuracy": _ratio(tp + tn, total),
        "accuracy_on_decisions": _ratio(tp + tn, decided),
        "false_positive_rate": _ratio(fp, decided_negative_labels),
        "false_negative_rate": _ratio(operational_fn, positive_support),
        "recall_on_decisions": _ratio(tp, decided_positive_labels),
        "decision_coverage": _ratio(decided, total),
        "positive_decision_coverage": _ratio(decided_positive_labels, positive_support),
        "negative_decision_coverage": _ratio(decided_negative_labels, negative_support),
        "abstention_rate": _ratio(abstain_positive + abstain_negative, total),
        "positive_support": positive_support,
        "negative_support": negative_support,
        "confidence_intervals_95": {
            "precision": _wilson(tp, predicted_positive),
            "recall": _wilson(tp, positive_support),
            "false_positive_rate": _wilson(fp, decided_negative_labels),
        },
        "semantics": {
            "positive_abstention": "counted as an operational missed alert for recall/FNR",
            "negative_abstention": "kept as an abstention and excluded from specificity/FPR denominators",
            "accuracy": "correct decided predictions divided by all labeled cases, so abstentions reduce accuracy",
        },
        "note": (
            "Metrics are valid only for an independently labeled, representative holdout set. "
            "Abstentions are explicit and never treated as benign predictions."
        ),
    }
    return result


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
