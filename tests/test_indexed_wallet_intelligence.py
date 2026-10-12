"""Offline contract tests: no network, no database, no fabricated provider responses in production."""
import pytest
from fastapi import HTTPException
from src.api import indexed_transfer_routes as routes


@pytest.mark.asyncio
async def test_invalid_wallet_address_rejected():
    with pytest.raises(HTTPException) as error:
        await routes.wallet_indexed_transfers("invalid-wallet")
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_report_citations_and_no_unsupported_risk_claim(monkeypatch):
    address = "0x" + "a" * 40
    counterparty = "0x" + "b" * 40
    tx_hash = "0x" + "1" * 64

    async def fake_lookup(*args):
        return {
            "transfers": [{
                "hash": tx_hash,
                "from_address": address,
                "to_address": counterparty,
                "asset": "ETH",
                "category": "external",
                "evidence_url": "https://etherscan.io/tx/" + tx_hash,
            }],
            "outgoing_next_page_key": None,
            "incoming_next_page_key": None,
            "coverage": "Test bounded transfer page",
        }

    monkeypatch.setattr(routes, "wallet_indexed_transfers", fake_lookup)
    report = await routes.wallet_evidence_report(address)
    assert report["observed_unique_transfers"] == 1
    assert report["outgoing_count"] == 1
    assert report["incoming_count"] == 0
    assert report["unique_counterparties"] == 1
    assert report["evidence"][0]["tx_hash"] == tx_hash
    assert report["risk_assessment"]["status"] == "not_assessed"
    assert report["historical_completeness"] is False


@pytest.mark.asyncio
async def test_graph_edges_reference_real_transaction_hashes(monkeypatch):
    address = "0x" + "a" * 40
    counterparty = "0x" + "b" * 40
    tx_hash = "0x" + "2" * 64

    async def fake_lookup(*args):
        return {
            "transfers": [{
                "hash": tx_hash,
                "from_address": address,
                "to_address": counterparty,
                "asset": "ETH",
                "category": "external",
                "value": 1.0,
                "block_number_hex": "0x123",
                "evidence_url": "https://etherscan.io/tx/" + tx_hash,
            }],
            "outgoing_next_page_key": "next",
            "incoming_next_page_key": None,
            "coverage": "Test bounded transfer page",
        }

    monkeypatch.setattr(routes, "wallet_indexed_transfers", fake_lookup)
    graph = await routes.wallet_indexed_graph(address)
    assert graph["depth"] == 1
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["tx_hash"] == tx_hash
    assert graph["next_page_keys"]["outgoing"] == "next"
    assert graph["historical_completeness"] is False
