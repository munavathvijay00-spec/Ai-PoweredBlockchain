"""Guard against silently committing an incompletely scored block."""
import pytest
from src.ingest.worker import require_complete_normalization


def test_normalization_rejects_missing_transactions():
    with pytest.raises(ValueError, match="Incomplete block normalization"):
        require_complete_normalization([{"hash": "x"}], [])


def test_normalization_rejects_duplicate_hashes():
    tx = {"hash": "0x" + "a" * 64}
    with pytest.raises(ValueError, match="duplicate"):
        require_complete_normalization([tx, tx], [tx, tx])
