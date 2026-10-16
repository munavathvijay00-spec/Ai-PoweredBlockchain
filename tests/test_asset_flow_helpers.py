from decimal import Decimal

from src.api.graph_routes import _decimal_amount


def test_decimal_amount_accepts_provider_numeric_text():
    assert _decimal_amount("123.4500") == Decimal("123.4500")
    assert _decimal_amount(2) == Decimal("2")


def test_decimal_amount_rejects_non_numeric_or_negative_values():
    assert _decimal_amount(None) is None
    assert _decimal_amount("") is None
    assert _decimal_amount("not-a-number") is None
    assert _decimal_amount("NaN") is None
    assert _decimal_amount("-1") is None
