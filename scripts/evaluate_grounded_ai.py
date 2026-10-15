"""Evaluate ChainScope AI grounding against an independently authored holdout set.

Input JSONL: one object per line with:
- case_id: unique identifier
- baseline: deterministic ChainScope source-of-truth explanation
- candidate: model explanation to evaluate
- expected_grounded: boolean assigned independently of the grounding checker
- tx: optional transaction context used by the production checker

This benchmark measures the grounding gate itself. It does not measure fraud
detection accuracy and it must not reuse detector/model outputs as labels.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from src.agents.explainer import grounding_report


def _ratio(num: int, den: int):
    return num / den if den else None


def evaluate_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    reasons = Counter()
    seen: set[str] = set()
    total = 0

    for case in cases:
        total += 1
        case_id = str(case.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("case_id must be nonempty")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)

        expected = case.get("expected_grounded")
        if not isinstance(expected, bool):
            raise ValueError(f"case {case_id}: expected_grounded must be boolean")
        baseline = case.get("baseline")
        candidate = case.get("candidate")
        if not isinstance(baseline, str) or not baseline.strip():
            raise ValueError(f"case {case_id}: baseline must be nonempty text")
        if not isinstance(candidate, str):
            raise ValueError(f"case {case_id}: candidate must be text")

        report = grounding_report(candidate, baseline, case.get("tx"))
        predicted = bool(report.get("grounded"))
        for reason in report.get("reasons") or []:
            reasons[str(reason)] += 1

        if expected and predicted:
            counts["tp"] += 1
        elif not expected and predicted:
            counts["fp"] += 1
        elif not expected and not predicted:
            counts["tn"] += 1
        else:
            counts["fn"] += 1

    if total == 0:
        raise ValueError("no grounding benchmark cases supplied")

    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    positive_support = tp + fn
    negative_support = tn + fp
    accepted = tp + fp
    rejected = tn + fn

    return {
        "cases": total,
        "confusion_matrix": counts,
        "grounded_acceptance_precision": _ratio(tp, accepted),
        "grounded_acceptance_recall": _ratio(tp, positive_support),
        "unsupported_claim_rejection_rate": _ratio(tn, negative_support),
        "false_accept_rate": _ratio(fp, negative_support),
        "false_reject_rate": _ratio(fn, positive_support),
        "acceptance_rate": _ratio(accepted, total),
        "rejection_rate": _ratio(rejected, total),
        "reason_counts": dict(sorted(reasons.items())),
        "semantics": {
            "positive": "independently labeled as a faithful evidence-grounded rewrite",
            "negative": "independently labeled as containing unsupported, invented, or insufficiently specific content",
            "scope": "grounding-gate quality only; not transaction or fraud-detection accuracy",
        },
    }


def load_jsonl(path: str) -> list[dict[str, Any]]:
    cases = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: expected JSON object")
            cases.append(value)
    return cases


def main(path: str) -> None:
    print(json.dumps(evaluate_cases(load_jsonl(path)), indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/evaluate_grounded_ai.py benchmark.jsonl")
    try:
        main(sys.argv[1])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
