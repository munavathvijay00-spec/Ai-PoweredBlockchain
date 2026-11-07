from src.risk.evaluation import evaluate_predictions
import pytest


def test_independent_evaluation_keeps_abstention_explicit():
    result = evaluate_predictions([
        {"case_id": "a", "label": 1, "prediction": "1"},
        {"case_id": "b", "label": 0, "prediction": "1"},
        {"case_id": "c", "label": 1, "prediction": "abstain"},
        {"case_id": "d", "label": 0, "prediction": "0"},
    ])
    assert result["sample_size"] == 4
    assert result["abstentions"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["decision_coverage"] == 0.75
    assert result["confidence_intervals_95"]["precision"] is not None


def test_duplicate_case_ids_are_rejected():
    try:
        evaluate_predictions([
            {"case_id": "a", "label": 1, "prediction": "1"},
            {"case_id": "a", "label": 0, "prediction": "0"},
        ])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate case IDs must fail")


@pytest.mark.parametrize("bad_label", [0.5, 1.0, 1.9, True, None, "", "false", -1, 2])
def test_invalid_ground_truth_is_never_coerced(bad_label):
    with pytest.raises(ValueError):
        evaluate_predictions([{"case_id": "case-a", "label": bad_label, "prediction": "1"}])


@pytest.mark.parametrize("bad_id", [None, 123, "", "  ", "\n"])
def test_missing_case_identifiers_are_rejected(bad_id):
    with pytest.raises(ValueError):
        evaluate_predictions([{"case_id": bad_id, "label": 1, "prediction": "1"}])


def test_whitespace_normalization_prevents_duplicate_cases():
    with pytest.raises(ValueError):
        evaluate_predictions([
            {"case_id": "case-a", "label": 1, "prediction": 1},
            {"case_id": " case-a ", "label": 0, "prediction": 0},
        ])
