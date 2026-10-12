"""Deterministic evaluation of evidence classifications against independently labeled cases.

Labels: 1 = independently established suspicious, 0 = independently established benign.
Unknown assessments are abstentions, never silently counted as negatives.
"""
from collections import Counter


def evaluate_labeled_cases(cases):
    counts = Counter()
    for case in cases:
        label = case["label"]
        prediction = case["prediction"]
        if label not in (0, 1) or prediction not in ("review", "insufficient_evidence"):
            raise ValueError("invalid benchmark label or prediction")
        if prediction == "insufficient_evidence":
            counts["abstained"] += 1
            counts["false_negative" if label == 1 else "true_negative"] += 1
            continue
        if label == 1:
            counts["true_positive"] += 1
        else:
            counts["false_positive"] += 1
    n = len(cases)
    tp, fp = counts["true_positive"], counts["false_positive"]
    # Operational triage evaluation: an abstained positive is a missed alert.\n    # Abstention is NOT a claim that the transaction is benign.
    return {
        "sample_size": n,
        "reviewed": tp + fp,
        "abstained": counts["abstained"],
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": counts["false_negative"],
        "true_negative": counts["true_negative"],
        "precision_on_reviewed": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + counts["false_negative"]) if tp + counts["false_negative"] else None,
        "false_positive_rate": fp / (fp + counts["true_negative"]) if fp + counts["true_negative"] else None,
        "false_negative_rate": counts["false_negative"] / (tp + counts["false_negative"]) if tp + counts["false_negative"] else None,
        "coverage": (tp + fp) / n if n else None,
        "calibrated": False,
        "note": "Operational missed-alert accounting counts abstained positives as false negatives; abstention is not a benign classification. Rates are meaningful only with a representative, independently labeled validation set.",
    }
