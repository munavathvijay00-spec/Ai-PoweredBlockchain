"""Fail closed on malformed or unattributed official Ethereum address records."""
from src.risk.official_entities import OFFICIAL_ENTITY_RECORDS

def test_registry_has_unique_exact_mainnet_addresses():
    addresses = []
    for entry in OFFICIAL_ENTITY_RECORDS:
        address = entry["address"]
        assert address.startswith("0x") and len(address) == 42
        assert all(char in "0123456789abcdef" for char in address[2:].lower())
        assert entry["source_url"].startswith("https://")
        assert entry["entity_name"].strip()
        assert entry["evidence"]["publisher"].strip()
        assert 0 <= entry["confidence"] <= 1
        addresses.append(address.lower())
    assert len(addresses) == len(set(addresses)), "Duplicate official entity addresses"
