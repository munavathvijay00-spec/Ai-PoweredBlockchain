from src.risk.evaluation import evaluate_predictions


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
