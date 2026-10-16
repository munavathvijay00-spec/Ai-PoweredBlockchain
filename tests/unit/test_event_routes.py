import pytest

from src.api import event_routes


class _FakeEth:
    async def get_transaction_receipt(self, tx_hash):
        return {"transactionHash": tx_hash, "blockNumber": 123, "logs": []}


class _FakeWeb3:
    def __init__(self, provider):
        self.provider = provider
        self.eth = _FakeEth()


class _FakeProvider:
    """Matches web3 6.15 lifecycle: intentionally has no disconnect method."""

    def __init__(self, rpc_url, request_kwargs=None):
        self.rpc_url = rpc_url
        self.request_kwargs = request_kwargs or {}


@pytest.mark.asyncio
async def test_receipt_lookup_does_not_require_provider_disconnect(monkeypatch):
    monkeypatch.setattr(event_routes, "_rpc_candidates", lambda: ["https://rpc.example"])
    monkeypatch.setattr(event_routes, "AsyncHTTPProvider", _FakeProvider)
    monkeypatch.setattr(event_routes, "AsyncWeb3", _FakeWeb3)

    tx_hash = "0x" + "a" * 64
    receipt, w3 = await event_routes._receipt_from_rpc(tx_hash)

    assert receipt["transactionHash"] == tx_hash
    assert receipt["blockNumber"] == 123
    assert isinstance(w3.provider, _FakeProvider)
    assert not hasattr(w3.provider, "disconnect")
