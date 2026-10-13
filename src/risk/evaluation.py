"""Detection evaluation against independent labels.

No metric is meaningful unless labels come from an independent source. Abstention
is kept explicit rather than silently converted to a benign prediction.
"""
import math


def _ratio(num, den):
    return num / den if den else None


def wilson_interval(successes, total, z=1.959963984540054):
    if not total:
        return None
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def evaluate_predictions(rows):
    """Rows require case_id, label (0/1), prediction (0/1/abstain)."""
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "abstain_positive": 0, "abstain_negative": 0}
    seen = set()
    for row in rows:
        case_id = str(row["case_id"])
        if not case_id or case_id in seen:
            raise ValueError("case_id must be nonempty and unique")
        seen.add(case_id)
        label = int(row["label"])
        prediction = str(row["prediction"])
        if label not in (0, 1) or prediction not in {"0", "1", "abstain"}:
            raise ValueError("invalid label or prediction")
        if prediction == "abstain":
            counts["abstain_positive" if label else "abstain_negative"] += 1
        elif prediction == "1":
            counts["tp" if label else "fp"] += 1
        else:
            counts["fn" if label else "tn"] += 1

    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    ap, an = counts["abstain_positive"], counts["abstain_negative"]
    total = len(seen)
    decided = tp + fp + tn + fn
    positive_support = tp + fn + ap
    negative_support = tn + fp + an
    predicted_positive = tp + fp
    operational_fn = fn + ap
    decided_negative_labels = tn + fp
    return {
        "sample_size": total,
        "decided_cases": decided,
        "abstentions": ap + an,
        "confusion_matrix": counts,
        "precision": _ratio(tp, predicted_positive),
        "recall": _ratio(tp, positive_support),
        "specificity": _ratio(tn, decided_negative_labels),
        "f1": _ratio(2 * tp, 2 * tp + fp + operational_fn),
        "accuracy": _ratio(tp + tn, total),
        "decision_coverage": _ratio(decided, total),
        "false_positive_rate": _ratio(fp, decided_negative_labels),
        "false_negative_rate": _ratio(operational_fn, positive_support),
        "positive_support": positive_support,
        "negative_support": negative_support,
        "confidence_intervals_95": {
            "precision": wilson_interval(tp, predicted_positive),
            "recall": wilson_interval(tp, positive_support),
            "false_positive_rate": wilson_interval(fp, decided_negative_labels),
        },
        "calibrated": False,
        "note": "Valid only for an independently labelled, representative holdout set. Abstentions are explicit and positive abstentions count as missed alerts for recall.",
    }
