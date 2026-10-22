"""Threshold analysis tests; illustrative labels are not real benchmark evidence."""
import pytest
from src.risk.threshold_diagnostics import threshold_diagnostics


def sample():
    return [
        {"case_id": "p1", "label": 1, "score": 80, "usable_evidence": True},
        {"case_id": "n1", "label": 0, "score": 50, "usable_evidence": True},
        {"case_id": "p2", "label": 1, "score": 25, "usable_evidence": False},
        {"case_id": "n2", "label": 0, "score": 5, "usable_evidence": True},
    ]


def test_reports_false_positives_and_abstentions():
    results = threshold_diagnostics(sample())
    assert [x["threshold"] for x in results["thresholds"]] == [20, 40, 80]
    at_40 = results["thresholds"][1]
    assert at_40["confusion_matrix"]["tp"] == 1
    assert at_40["confusion_matrix"]["fp"] == 1
    assert at_40["confusion_matrix"]["abstain_positive"] == 1
    assert at_40["false_positive_rate"] == 0.5
    assert at_40["recall"] == 0.5


def test_rejects_duplicate_cases():
    cases = sample()
    with pytest.raises(ValueError, match="unique"):
        threshold_diagnostics(cases + [cases[0]])


def test_empty_sample_does_not_claim_accuracy():
    response = threshold_diagnostics([])
    assert response["sample_size"] == 0
    assert response["thresholds"] == []


def test_invalid_score_and_threshold_rejected():
    cases = sample()
    cases[0]["score"] = 120
    with pytest.raises(ValueError, match="Scores"):
        threshold_diagnostics(cases)
    with pytest.raises(ValueError, match="threshold"):
        threshold_diagnostics(sample(), thresholds=(-1,))
