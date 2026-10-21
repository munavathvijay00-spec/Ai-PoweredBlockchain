"""Unit checks for bounded hot-table retention configuration."""
import pytest
from src.storage_budget import bounded_retention_minutes


@pytest.mark.parametrize("raw,expected", [(None,5),("",5),("5",5),("15",15),("60",60)])
def test_allowed_retention(raw, expected):
    assert bounded_retention_minutes(raw) == expected


@pytest.mark.parametrize("raw", ["0","4","61","5000","bad","4.5"])
def test_unsafe_retention_rejected(raw):
    with pytest.raises(ValueError):
        bounded_retention_minutes(raw)
