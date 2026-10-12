"""Read-only, bounded ERC-20 metadata resolution.

Metadata comes from contract eth_call, not from an independent token registry.
A symbol is never proof of asset identity or legitimacy.
"""
import asyncio
import re

from web3 import AsyncWeb3

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
SYMBOL_SELECTOR = "0x95d89b41"
DECIMALS_SELECTOR = "0x313ce567"


def parse_decimals(data):
    raw = data.hex() if isinstance(data, bytes) else str(data)
    raw = raw.removeprefix("0x")
    if len(raw) != 64:
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    return value if 0 <= value <= 36 else None


def parse_symbol(data):
    raw = data.hex() if isinstance(data, bytes) else str(data)
    raw = raw.removeprefix("0x")
    try:
        payload = bytes.fromhex(raw)
        if len(payload) == 32:
            return payload.rstrip(b"\x00").decode("utf-8").strip()[:32] or None
        if len(payload) >= 96 and int.from_bytes(payload[:32], "big") == 32:
            size = int.from_bytes(payload[32:64], "big")
            if 0 < size <= 64 and len(payload) >= 64 + size:
                return payload[64:64 + size].decode("utf-8").strip()[:32] or None
    except (ValueError, UnicodeDecodeError):
        pass
    return None


async def resolve_metadata(w3: AsyncWeb3, address: str, block_number: int):
    """Return contract-reported metadata with per-call timeouts, no persistent cache."""
    result = {"symbol": None, "decimals": None,
              "metadata_source": "unavailable", "metadata_verified": False}
    if not ADDRESS.fullmatch(address):
        return result
    async def call(selector):
        try:
            return await asyncio.wait_for(
                w3.eth.call({"to": AsyncWeb3.to_checksum_address(address), "data": selector},
                            block_identifier=block_number), timeout=2)
        except Exception:
            return None
    symbol_data, decimals_data = await asyncio.gather(call(SYMBOL_SELECTOR), call(DECIMALS_SELECTOR))
    result["symbol"] = parse_symbol(symbol_data) if symbol_data is not None else None
    result["decimals"] = parse_decimals(decimals_data) if decimals_data is not None else None
    if result["symbol"] is not None or result["decimals"] is not None:
        result["metadata_source"] = "contract_eth_call_at_receipt_block"
    return result
