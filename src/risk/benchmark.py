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
            continue
        if label == 1:
            counts["true_positive"] += 1
        else:
            counts["false_positive"] += 1
    n = len(cases)
    tp, fp = counts["true_positive"], counts["false_positive"]
    # There is no negative decision in the current evidence classifier.
    # FN/TN are not measurable until a validated negative decision exists.
    return {
        "sample_size": n,
        "reviewed": tp + fp,
        "abstained": counts["abstained"],
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": None,
        "true_negative": None,
        "precision_on_reviewed": tp / (tp + fp) if tp + fp else None,
        "recall": None,
        "false_positive_rate": None,
        "false_negative_rate": None,
        "coverage": (tp + fp) / n if n else None,
        "calibrated": False,
        "note": "Abstentions are not negatives. No probability or sensitivity claims without a representative, independently labeled validation set.",
    }
