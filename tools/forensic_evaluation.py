"""Reproducible binary-detection and evidence-citation evaluation.

Input is JSON containing `cases`. Each case has `ground_truth` (0/1),
`predicted` (0/1), and optional `claims` entries with `cited_ids`,
`valid_ids`, `supported`, and `material_evidence_ids`.
No scores are reported when their denominator is zero.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def ratio(num: int, denom: int) -> float | None:
    return round(num / denom, 6) if denom else None


def evaluate(cases: list[dict]) -> dict:
    tp = fp = tn = fn = 0
    claim_count = supported_count = citations = valid_citations = 0
    evidence_expected = evidence_found = 0
    for case in cases:
        truth, predicted = case["ground_truth"], case["predicted"]
        if type(truth) is not int or truth not in (0, 1) or type(predicted) is not int or predicted not in (0, 1):
            raise ValueError("ground_truth and predicted must be binary integers")
        if truth and predicted:
            tp += 1
        elif not truth and predicted:
            fp += 1
        elif not truth and not predicted:
            tn += 1
        else:
            fn += 1

        for claim in case.get("claims", []):
            claim_count += 1
            supported_count += int(claim.get("supported") is True)
            cited = set(claim.get("cited_ids", []))
            valid = set(claim.get("valid_ids", []))
            citations += len(cited)
            valid_citations += len(cited & valid)
            material = set(claim.get("material_evidence_ids", []))
            evidence_expected += len(material)
            evidence_found += len(material & cited)
    return {
        "sample_count": len(cases),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "risk_detection": {
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "false_positive_rate": ratio(fp, fp + tn),
            "specificity": ratio(tn, tn + fp),
            "f1": ratio(2 * tp, 2 * tp + fp + fn),
        },
        "ai_findings": {
            "supported_claim_rate": ratio(supported_count, claim_count),
            "unsupported_claim_rate": ratio(claim_count - supported_count, claim_count),
            "citation_precision": ratio(valid_citations, citations),
            "material_evidence_recall": ratio(evidence_found, evidence_expected),
            "claims_evaluated": claim_count,
        },
        "limitations": [
            "Only manually independently labeled ground truth supports forensic quality claims.",
            "A case can contain multiple correlated findings; split by wallet, entity and time period.",
            "Null metrics indicate insufficient denominator, not zero risk.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text())
    report = evaluate(payload["cases"])
    output = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
