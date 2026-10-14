from types import SimpleNamespace

from src.api.historical_routes import _alchemy_rpc_url


def test_historical_provider_uses_dedicated_alchemy_key():
    settings = SimpleNamespace(
        alchemy_api_key="abc123",
        ethereum_rpc_url="https://ethereum-rpc.publicnode.com",
    )
    assert _alchemy_rpc_url(settings) == "https://eth-mainnet.g.alchemy.com/v2/abc123"


def test_placeholder_alchemy_keys_are_not_treated_as_provider_ready():
    for value in ("", "not-set", "unused", "dummy", "dummy_key_for_ci"):
        settings = SimpleNamespace(alchemy_api_key=value)
        assert _alchemy_rpc_url(settings) is None
