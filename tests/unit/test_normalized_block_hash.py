"""Canonical Ethereum block provenance survives transaction normalization."""
import pytest
from src.blockchain.normalizer import TransactionNormalizer


def transaction():
    return {
        "hash": "0x" + "c" * 64,
        "from": "0x" + "1" * 40,
        "to": "0x" + "2" * 40,
        "value": 1,
    }


def test_block_hash_is_preserved_and_canonicalized():
    result = TransactionNormalizer().normalize(
        transaction(),
        {"number": 123, "timestamp": 1700000000, "hash": "0x" + "AB" * 32},
    )
    assert result["block_hash"] == "0x" + "ab" * 32


def test_missing_legacy_block_hash_is_explicitly_unknown():
    result = TransactionNormalizer().normalize(
        transaction(), {"number": 123, "timestamp": 1700000000},
    )
    assert result["block_hash"] is None


def test_invalid_block_hash_is_not_silently_normalized():
    with pytest.raises(ValueError, match="32-byte hexadecimal"):
        TransactionNormalizer().normalize(
            transaction(),
            {"number": 123, "timestamp": 1700000000, "hash": "0x" + "z" * 64},
        )
