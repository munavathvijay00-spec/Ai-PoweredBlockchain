"""Threshold sensitivity analysis over independent labels.

Diagnostic only: no threshold optimization, calibration, or policy changes are
made from these results. Report both selective and end-to-end performance.
"""
from src.risk.evaluation import evaluate_predictions


def threshold_diagnostics(cases, thresholds=(20, 40, 80)):
    """cases: unique case_id, binary label, numeric score, usable_evidence."""
    if not cases:
        return {"sample_size": 0, "thresholds": [], "limitations": [
            "No independent labeled observations were supplied."]}
    ids = [str(case["case_id"]) for case in cases]
    if len(set(ids)) != len(ids) or any(not value for value in ids):
        raise ValueError("Independent case identifiers must be non-empty and unique")
    if any(int(case["label"]) not in (0, 1) for case in cases):
        raise ValueError("Labels must be binary")
    if any(isinstance(case["score"], bool) or not 0 <= float(case["score"]) <= 100 for case in cases):
        raise ValueError("Scores must be within 0..100")
    findings = []
    for threshold in thresholds:
        if not 0 <= int(threshold) <= 100:
            raise ValueError("Invalid threshold")
        rows = [{
            "case_id": case["case_id"],
            "label": case["label"],
            "prediction": ("abstain" if not case["usable_evidence"] else
                           "1" if float(case["score"]) >= threshold else "0"),
        } for case in cases]
        metrics = evaluate_predictions(rows)
        findings.append({"threshold": int(threshold), **metrics})
    return {
        "sample_size": len(cases),
        "thresholds": findings,
        "limitations": [
            "A balanced or selectively sampled corpus cannot estimate live prevalence or deployed alert precision.",
            "Missing behavioral history and entity signals can cause abstentions; abstentions are not benign predictions.",
            "Threshold comparison on this sample does not justify selecting a threshold without an independent holdout.",
            "These metrics do not calibrate the score as a probability of fraud.",
        ],
    }
