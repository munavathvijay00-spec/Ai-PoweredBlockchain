"""Offline tests for OFAC parsing: never depend on network or live sanctions data."""
import csv
import io
import pytest

from src.risk.ofac_intelligence import parse_ofac_eth_csv


def csv_payload(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    for entity_id, name, remarks in rows:
        writer.writerow([entity_id, name] + [""] * 9 + [remarks])
    return out.getvalue().encode()


def test_only_explicit_eth_address_is_verified():
    eth = "0x" + "a" * 40
    btc = "bc1q" + "b" * 38
    payload = csv_payload([
        ("123", "Listed entity", f"Digital Currency Address - ETH {eth}; Digital Currency Address - XBT {btc}"),
        ("456", "Other entity", "No digital currency addresses"),
    ])
    assert parse_ofac_eth_csv(payload) == {eth: ("123", "Listed entity")}


def test_rejects_empty_or_unparseable_feed():
    with pytest.raises(ValueError):
        parse_ofac_eth_csv(b"")
    with pytest.raises(ValueError):
        parse_ofac_eth_csv(csv_payload([("123", "No ETH", "Digital Currency Address - XBT 123")]))


def test_rejects_non_eth_tag_and_invalid_address():
    fake = "0x" + "f" * 40
    payload = csv_payload([("123", "Entity", f"Wallet {fake}; Digital Currency Address - ETH 0x123")])
    with pytest.raises(ValueError):
        parse_ofac_eth_csv(payload)


def test_case_normalization_and_deduplication():
    eth = "0x" + "aB" * 20
    payload = csv_payload([("123", "Entity", f"Digital Currency Address - ETH {eth}; Digital Currency Address - ETH {eth}")])
    assert list(parse_ofac_eth_csv(payload)) == [eth.lower()]
