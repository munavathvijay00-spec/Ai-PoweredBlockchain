"""Unit coverage for non-destructive ingestion and logical storage warnings."""
import pytest
from src.ingest.health_monitor import assess_ingestion_health, assess_storage_health


def test_ingestion_health_reports_lag_and_warning():
    result = assess_ingestion_health(120, 100)
    assert result["lag_blocks"] == 20
    assert result["warning"] is True
    assert result["chain_behind_checkpoint"] is False


def test_ingestion_health_at_tip_and_reorg():
    assert assess_ingestion_health(100, 100)["lag_blocks"] == 0
    result = assess_ingestion_health(90, 100)
    assert result["chain_behind_checkpoint"] is True
    assert result["lag_blocks"] == 0


def test_storage_warning_thresholds():
    mb = 1048576
    assert assess_storage_health(100 * mb)["level"] == "ok"
    assert assess_storage_health(350 * mb)["level"] == "warning"
    assert assess_storage_health(425 * mb)["level"] == "critical"


def test_invalid_thresholds_fail_closed():
    with pytest.raises(ValueError):
        assess_ingestion_health(10, 9, warn_lag=0)
    with pytest.raises(ValueError):
        assess_storage_health(0, budget_mb=0)
