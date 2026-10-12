"""Reject inconsistent transaction membership within an RPC block snapshot."""
import pytest
from src.ingest.worker import validate_block_snapshot


BLOCK_HASH = "0x" + "a" * 64
OTHER_HASH = "0x" + "b" * 64


def test_matching_membership_fields_are_accepted():
    validate_block_snapshot({
        "number": 123, "hash": BLOCK_HASH,
        "transactions": [{"hash": "0x" + "c" * 64, "blockNumber": 123, "blockHash": BLOCK_HASH}],
    }, 123)


def test_mismatched_transaction_block_hash_rejected():
    with pytest.raises(ValueError, match="block hash differs"):
        validate_block_snapshot({
            "number": 123, "hash": BLOCK_HASH,
            "transactions": [{"blockNumber": 123, "blockHash": OTHER_HASH}],
        }, 123)


def test_mismatched_transaction_height_rejected():
    with pytest.raises(ValueError, match="block number differs"):
        validate_block_snapshot({
            "number": 123, "hash": BLOCK_HASH,
            "transactions": [{"blockNumber": 124, "blockHash": BLOCK_HASH}],
        }, 123)


def test_transaction_block_hash_without_header_hash_rejected():
    with pytest.raises(ValueError, match="Canonical block hash missing"):
        validate_block_snapshot({
            "number": 123,
            "transactions": [{"blockNumber": 123, "blockHash": BLOCK_HASH}],
        }, 123)


def test_invalid_header_hash_rejected():
    with pytest.raises(ValueError, match="hexadecimal"):
        validate_block_snapshot({
            "number": 123, "hash": "0x" + "g" * 64, "transactions": [],
        }, 123)


def test_missing_transaction_block_number_rejected():
    with pytest.raises(ValueError, match="block number missing"):
        validate_block_snapshot({
            "number": 123, "hash": BLOCK_HASH,
            "transactions": [{"blockHash": BLOCK_HASH}],
        }, 123)


def test_missing_transaction_block_hash_rejected():
    with pytest.raises(ValueError, match="block hash missing"):
        validate_block_snapshot({
            "number": 123, "hash": BLOCK_HASH,
            "transactions": [{"blockNumber": 123}],
        }, 123)
