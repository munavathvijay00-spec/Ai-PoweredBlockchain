"""Malformed transaction hashes must not enter a checkpointed block."""
import pytest
from src.ingest.worker import require_complete_normalization


@pytest.mark.parametrize("bad_hash", [
    "0x" + "g" * 64,
    "0x" + "z" * 64,
    "0x" + "a" * 63,
    "0X" + "a" * 64,
    None,
])
def test_rejects_malformed_transaction_hash(bad_hash):
    with pytest.raises(ValueError, match="invalid transaction hashes"):
        require_complete_normalization(
            [{"hash": "original"}], [{"hash": bad_hash}]
        )


def test_accepts_valid_transaction_hash():
    require_complete_normalization(
        [{"hash": "original"}], [{"hash": "0x" + "aB" * 32}]
    )
