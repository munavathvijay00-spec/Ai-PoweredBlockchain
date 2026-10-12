"""A partial normalized block must never be marked ingested."""
import pytest
from src.ingest.worker import require_complete_normalization


def tx(char):
    return {"hash": "0x" + char * 64}


def test_all_transactions_normalized():
    rows = [tx("a"), tx("b")]
    require_complete_normalization(rows, rows)


def test_empty_block_is_valid():
    require_complete_normalization([], [])


def test_silent_normalizer_skip_is_fatal():
    with pytest.raises(ValueError, match="Incomplete block normalization"):
        require_complete_normalization([tx("a"), tx("b")], [tx("a")])


def test_duplicate_hash_is_fatal():
    with pytest.raises(ValueError, match="duplicate"):
        require_complete_normalization([tx("a"), tx("b")], [tx("a"), tx("a")])


def test_invalid_hash_is_fatal():
    with pytest.raises(ValueError, match="invalid"):
        require_complete_normalization([tx("a")], [{"hash": "0x123"}])
