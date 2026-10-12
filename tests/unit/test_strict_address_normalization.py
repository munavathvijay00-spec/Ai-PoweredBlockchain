"""Address normalization must never invent or truncate blockchain identities."""
import pytest
from src.blockchain.normalizer import TransactionNormalizer


def test_valid_address_normalizes_case():
    value = "0x" + "Ab" * 20
    assert TransactionNormalizer._to_address_string(value) == "0x" + "ab" * 20


@pytest.mark.parametrize("invalid", [
    "0x123", "0x" + "a" * 41, "0x" + "a" * 41 + "g",
    "0x" + "b" * 41 + "0", "not_an_address",
])
def test_malformed_address_rejected(invalid):
    with pytest.raises(ValueError, match="Invalid Ethereum address"):
        TransactionNormalizer._to_address_string(invalid)


def test_contract_creation_recipient_is_explicit_zero_address():
    assert TransactionNormalizer._to_address_string(None) == "0x" + "0" * 40
