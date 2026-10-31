"""Focused regression tests for external baseline reporting.

Run: python -m pytest tests/test_external_baseline.py -q
"""
import numpy as np

from scripts.evaluate_rule_baseline import extract_features, metrics


def test_confusion_matrix_and_false_positive_rate():
    result = metrics(np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1]))
    assert result["true_negative"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["true_positive"] == 1
    assert result["false_positive_rate"] == 0.5
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_external_features_do_not_include_labels_or_addresses():
    row = {
        "value_wei_text": "1000000000000000000",
        "gas": 21000,
        "gas_price_text": "1000000000",
        "label": 1,
        "from_address": "0x" + "a" * 40,
    }
    feature_vector = extract_features(row)
    assert len(feature_vector) == 3
    assert all(np.isfinite(feature_vector))
    row["label"] = 0
    row["from_address"] = "0x" + "b" * 40
    assert feature_vector == extract_features(row)


def test_empty_positive_prediction_is_safe():
    result = metrics(np.array([0, 1]), np.array([0, 0]))
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["false_negative"] == 1
