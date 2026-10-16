import re

from src.risk.official_entities import OFFICIAL_ENTITY_RECORDS

ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")


def test_official_entity_registry_has_unique_normalized_addresses():
    addresses = [row["address"] for row in OFFICIAL_ENTITY_RECORDS]
    assert all(ADDRESS.fullmatch(address) for address in addresses)
    assert len(addresses) == len(set(addresses))


def test_official_entity_registry_requires_provenance():
    for row in OFFICIAL_ENTITY_RECORDS:
        assert row["source"]
        assert row["entity_id"]
        assert row["entity_name"]
        assert row["entity_type"] in {"protocol", "contract", "token", "infrastructure"}
        assert row["confidence"] == 1.0
        assert str(row["source_url"]).startswith("https://")
        assert row["evidence"].get("publisher")
        assert row["evidence"].get("method")
