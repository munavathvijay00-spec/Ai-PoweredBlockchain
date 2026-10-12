from src.risk.benchmark import evaluate_labeled_cases


def test_benchmark_counts_false_positives_and_missed_alerts():
    result = evaluate_labeled_cases([
        {"label": 1, "prediction": "review"},
        {"label": 0, "prediction": "review"},
        {"label": 1, "prediction": "insufficient_evidence"},
        {"label": 0, "prediction": "insufficient_evidence"},
    ])
    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["true_negative"] == 1
    assert result["coverage"] == 0.5
    assert result["recall"] == 0.5
    assert result["false_positive_rate"] == 0.5


def test_empty_benchmark_has_no_invented_metrics():
    result = evaluate_labeled_cases([])
    assert result["precision_on_reviewed"] is None
    assert result["false_negative_rate"] is None
    assert result["calibrated"] is False
