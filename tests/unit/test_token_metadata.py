"""ERC-20 contract metadata parsing regression tests."""
from src.blockchain.token_metadata import parse_decimals, parse_symbol


def test_decimals_uint8():
    assert parse_decimals(bytes.fromhex("0" * 62 + "12")) == 18
    assert parse_decimals(bytes.fromhex("0" * 62 + "ff")) is None


def test_symbol_legacy_bytes32():
    assert parse_symbol(b"USDC" + bytes(28)) == "USDC"


def test_symbol_dynamic_string():
    payload = (32).to_bytes(32, "big") + (4).to_bytes(32, "big") + b"USDT" + bytes(28)
    assert parse_symbol(payload) == "USDT"


def test_malformed_metadata():
    assert parse_symbol("0xzz") is None
    assert parse_decimals("0x") is None
