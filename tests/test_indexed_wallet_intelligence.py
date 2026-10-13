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
            "categories": ["external", "erc20", "internal", "erc721", "erc1155"],
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
    assert report["detection_quality"]["status"] == "not_evaluated"
    assert report["detection_quality"]["abstention_supported"] is True
    assert report["coverage_details"]["categories"] == [
        "external", "erc20", "internal", "erc721", "erc1155"
    ]
    assert report["historical_completeness"] is False


@pytest.mark.asyncio
async def test_graph_edges_reference_real_transaction_hashes(monkeypatch):
    address = "0x" + "a" * 40
    counterparty = "0x" + "b" * 40
    tx_hash = "0x" + "2" * 64

    async def fake_lookup(*args):
        return {
            "categories": ["external", "erc20"],
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


@pytest.mark.asyncio
async def test_provider_rejects_non_json_payload():
    class FakeResponse:
        status = 200
        async def json(self, content_type=None):
            return ["unexpected", "payload"]
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(HTTPException) as error:
        await routes._transfer_page(
            FakeSession(), "https://eth-mainnet.g.alchemy.com/v2/test",
            "0x" + "a" * 40, "fromAddress", 2
        )
    assert error.value.status_code == 502


@pytest.mark.asyncio
async def test_transfer_pagination_and_self_transfer_dedup(monkeypatch):
    address = "0x" + "a" * 40
    tx_hash = "0x" + "3" * 64

    class Settings:
        ethereum_rpc_url = "https://eth-mainnet.g.alchemy.com/v2/test"

    calls = []

    async def fake_page(session, rpc_url, wallet, direction, count, page_key=None, categories=None):
        calls.append((direction, count, page_key, tuple(categories or [])))
        return {
            "transfers": [{
                "uniqueId": "unique-transfer-1",
                "hash": tx_hash,
                "from": address,
                "to": address,
                "category": "external",
                "asset": "ETH",
                "value": 0.5,
                "blockNum": "0x123",
            }],
            "pageKey": "next-" + direction,
        }

    monkeypatch.setattr(routes, "get_settings", lambda: Settings())
    monkeypatch.setattr(routes, "_transfer_page", fake_page)
    result = await routes.wallet_indexed_transfers(
        address, 2, "outgoing-cursor", "incoming-cursor"
    )
    expected_categories = ("external", "erc20", "internal", "erc721", "erc1155")
    assert result["returned"] == 1
    assert result["categories"] == list(expected_categories)
    assert result["outgoing_next_page_key"] == "next-fromAddress"
    assert result["incoming_next_page_key"] == "next-toAddress"
    assert ("fromAddress", 2, "outgoing-cursor", expected_categories) in calls
    assert ("toAddress", 2, "incoming-cursor", expected_categories) in calls
    assert result["historical_completeness"] is False


@pytest.mark.asyncio
async def test_nft_metadata_is_preserved(monkeypatch):
    address = "0x" + "a" * 40
    other = "0x" + "b" * 40
    tx_hash = "0x" + "4" * 64

    class Settings:
        ethereum_rpc_url = "https://eth-mainnet.g.alchemy.com/v2/test"

    async def fake_page(session, rpc_url, wallet, direction, count, page_key=None, categories=None):
        if direction == "toAddress":
            return {"transfers": [], "pageKey": None}
        return {
            "transfers": [{
                "uniqueId": "nft-transfer-1",
                "hash": tx_hash,
                "from": address,
                "to": other,
                "category": "erc721",
                "asset": "COLLECTIBLE",
                "tokenId": "0x2a",
                "value": None,
                "rawContract": {"address": "0x" + "c" * 40},
                "blockNum": "0x123",
            }],
            "pageKey": None,
        }

    monkeypatch.setattr(routes, "get_settings", lambda: Settings())
    monkeypatch.setattr(routes, "_transfer_page", fake_page)
    result = await routes.wallet_indexed_transfers(address)
    transfer = result["transfers"][0]
    assert transfer["category"] == "erc721"
    assert transfer["token_id"] == "0x2a"
    assert transfer["raw_contract"]["address"] == "0x" + "c" * 40


@pytest.mark.asyncio
async def test_rejects_malicious_lookalike_alchemy_host(monkeypatch):
    class Settings:
        ethereum_rpc_url = "https://alchemy.com.attacker.example/v2/test"

    monkeypatch.setattr(routes, "get_settings", lambda: Settings())
    with pytest.raises(HTTPException) as error:
        await routes.wallet_indexed_transfers("0x" + "a" * 40)
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_only_pending_direction_is_queried(monkeypatch):
    address = "0x" + "a" * 40
    class Settings:
        ethereum_rpc_url = "https://eth-mainnet.g.alchemy.com/v2/test"
    calls = []
    async def fake_page(session, rpc_url, wallet, direction, count, page_key=None, categories=None):
        calls.append((direction, page_key))
        return {"transfers": [], "pageKey": None}
    monkeypatch.setattr(routes, "get_settings", lambda: Settings())
    monkeypatch.setattr(routes, "_transfer_page", fake_page)
    result = await routes.wallet_indexed_transfers(
        address, 25, None, "next-incoming", False, True
    )
    assert calls == [("toAddress", "next-incoming")]
    assert result["queried_directions"] == ["incoming"]
    assert result["outgoing_next_page_key"] is None


@pytest.mark.asyncio
async def test_scope_can_exclude_internal_and_nfts(monkeypatch):
    address = "0x" + "a" * 40
    class Settings:
        ethereum_rpc_url = "https://eth-mainnet.g.alchemy.com/v2/test"
    categories_seen = []
    async def fake_page(session, rpc_url, wallet, direction, count, page_key=None, categories=None):
        categories_seen.append(tuple(categories or []))
        return {"transfers": [], "pageKey": None}
    monkeypatch.setattr(routes, "get_settings", lambda: Settings())
    monkeypatch.setattr(routes, "_transfer_page", fake_page)
    result = await routes.wallet_indexed_transfers(
        address, 25, None, None, True, True, False, False
    )
    assert result["categories"] == ["external", "erc20"]
    assert categories_seen == [("external", "erc20"), ("external", "erc20")]


@pytest.mark.asyncio
async def test_both_directions_disabled_is_invalid():
    with pytest.raises(HTTPException) as error:
        await routes.wallet_indexed_transfers(
            "0x" + "a" * 40, 25, None, None, False, False
        )
    assert error.value.status_code == 422


def test_behavioral_rules_require_evidence_and_do_not_assign_fraud_label():
    root = "0x" + "a" * 40
    other = "0x" + "b" * 40
    records = [
        {"hash": "0x" + str(i) * 64, "from_address": root, "to_address": other}
        for i in (1, 2, 3)
    ]
    signals = routes._observed_behavioral_signals(records, root)
    assert len(signals) == 1
    assert signals[0]["code"] == "repeated_pair"
    assert len(signals[0]["evidence"]) == 3
    assert signals[0]["not_a_fraud_verdict"] is True
    assert routes._observed_behavioral_signals(records[:2], root) == []


def test_self_transfer_review_signal():
    root = "0x" + "a" * 40
    records = [{"hash": "0x" + "f" * 64, "from_address": root, "to_address": root}]
    signals = routes._observed_behavioral_signals(records, root)
    assert signals[0]["code"] == "self_transfer"
    assert signals[0]["evidence"][0]["url"].endswith("f" * 64)
