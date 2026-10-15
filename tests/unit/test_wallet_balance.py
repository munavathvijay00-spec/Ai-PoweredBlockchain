import pytest
from fastapi import HTTPException
from web3 import Web3

from src.api.wallet_routes import wallet_live_balance


LOWER_ADDRESS = "0x51c7c0078292e4a922815207bea22039b57e2a7f"


class _FakeEth:
    def __init__(self):
        self.requested_address = None
        self.requested_block = None

    async def get_balance(self, address, block_identifier=None):
        self.requested_address = address
        self.requested_block = block_identifier
        return 1_250_000_000_000_000_000


class _FakeWeb3:
    def __init__(self):
        self.eth = _FakeEth()


class _FakeBlockchainClient:
    instance = None

    def __init__(self):
        self.w3 = _FakeWeb3()
        self.closed = False
        type(self).instance = self

    async def connect(self):
        return True

    async def get_latest_block_number(self):
        return 23_456_789

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_wallet_balance_checksums_lowercase_address_before_rpc(monkeypatch):
    monkeypatch.setattr("src.blockchain.client.BlockchainClient", _FakeBlockchainClient)

    result = await wallet_live_balance(LOWER_ADDRESS)
    client = _FakeBlockchainClient.instance

    assert client.w3.eth.requested_address == Web3.to_checksum_address(LOWER_ADDRESS)
    assert client.w3.eth.requested_block == 23_456_789
    assert result["address"] == LOWER_ADDRESS
    assert result["balance_wei"] == "1250000000000000000"
    assert result["balance_eth"] == "1.25"
    assert result["block_number"] == 23_456_789
    assert result["chain_id"] == 1
    assert client.closed is True


@pytest.mark.asyncio
async def test_wallet_balance_rejects_invalid_address_before_rpc():
    with pytest.raises(HTTPException) as exc_info:
        await wallet_live_balance("not-an-address")

    assert exc_info.value.status_code == 422


class _FailingEth:
    async def get_balance(self, address, block_identifier=None):
        raise RuntimeError("upstream failure")


class _FailingClient(_FakeBlockchainClient):
    def __init__(self):
        self.w3 = type("FakeWeb3", (), {"eth": _FailingEth()})()
        self.closed = False
        type(self).instance = self


@pytest.mark.asyncio
async def test_wallet_balance_provider_failure_is_bounded_502(monkeypatch):
    monkeypatch.setattr("src.blockchain.client.BlockchainClient", _FailingClient)

    with pytest.raises(HTTPException) as exc_info:
        await wallet_live_balance(LOWER_ADDRESS)

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Could not retrieve verified Ethereum balance"
    assert _FailingClient.instance.closed is True
