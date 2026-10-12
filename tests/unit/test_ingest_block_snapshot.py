"""Prevent header-only or fork-mismatched snapshots from entering ingestion."""
import pytest
from src.ingest.worker import validate_block_snapshot


def test_valid_full_block_snapshot():
    validate_block_snapshot({
        "number": 123,
        "hash": "0x" + "a" * 64,
        "transactions": [{
            "hash": "0x" + "b" * 64,
            "blockNumber": 123,
            "blockHash": "0x" + "a" * 64,
        }],
    }, 123)
    validate_block_snapshot({"number": 123, "transactions": []}, 123)


def test_wrong_height_rejected():
    with pytest.raises(ValueError, match="height"):
        validate_block_snapshot({"number": 124, "transactions": []}, 123)


def test_hash_only_transactions_rejected():
    with pytest.raises(ValueError, match="full block"):
        validate_block_snapshot({"number": 123, "transactions": ["0xabc"]}, 123)


def test_missing_transaction_payload_rejected():
    with pytest.raises(ValueError, match="Full transaction"):
        validate_block_snapshot({"number": 123}, 123)
