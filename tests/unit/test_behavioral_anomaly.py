from datetime import datetime, timezone

from src.ml.anomaly import _feature_vector


def test_behavioral_feature_vector_is_finite_and_stable():
    row = {
        "value": 2 * 10**18,
        "gas_used": 21000,
        "gas_price": 30 * 10**9,
        "timestamp": datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc),
        "sender_tx_count": 14,
        "recipient_tx_count": 8,
        "sender_unique_counterparties": 5,
        "recipient_unique_counterparties": 3,
    }
    vector = _feature_vector(row)
    assert len(vector) == 11
    assert all(isinstance(value, float) for value in vector)
    assert all(value == value for value in vector)  # no NaN


def test_behavioral_feature_vector_handles_missing_values():
    vector = _feature_vector({})
    assert len(vector) == 11
    assert all(isinstance(value, float) for value in vector)
    assert all(value == value for value in vector)
