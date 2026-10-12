"""A missing Ethereum sender is not the zero address."""
import pytest
from src.blockchain.normalizer import TransactionNormalizer


@pytest.mark.parametrize("missing", [None, ""])
def test_missing_sender_is_rejected(missing):
    tx = {
        "hash": "0x" + "a" * 64,
        "from": missing,
        "to": "0x" + "2" * 40,
        "value": 1,
    }
    block = {"number": 1, "timestamp": 1700000000}
    with pytest.raises(ValueError, match="sender address is missing"):
        TransactionNormalizer().normalize(tx, block)


def test_contract_creation_without_recipient_remains_supported():
    tx = {
        "hash": "0x" + "a" * 64,
        "from": "0x" + "1" * 40,
        "to": None,
        "value": 1,
    }
    block = {"number": 1, "timestamp": 1700000000}
    normalized = TransactionNormalizer().normalize(tx, block)
    assert normalized["from_address"] == "0x" + "1" * 40
    assert normalized["to_address"] == "0x" + "0" * 40
