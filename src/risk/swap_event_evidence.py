"""Defensive swap event ABI decoding from Ethereum receipt logs.

The event signatures are:
Uniswap v2 Pair.Swap(address,uint256,uint256,uint256,uint256,address)
Uniswap v3 Pool.Swap(address,address,int256,int256,uint160,uint128,int24)

Unverified emitters can mimic either signature. Decode only the event shape,
never label an unknown emitting contract as an actual Uniswap pool.
"""
from __future__ import annotations

import re

V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
HEX_WORD = re.compile(r"^[0-9a-f]{64}$")
HEX_ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")


def _text_hex(value) -> str:
    if isinstance(value, str):
        return value.lower()
    if hasattr(value, "hex"):
        result = value.hex()
        return ("0x" if not result.startswith("0x") else "") + result.lower()
    return ""


def _address_topic(topic: str) -> str | None:
    if len(topic) != 66 or not topic.startswith("0x") or not HEX_WORD.fullmatch(topic[2:]):
        return None
    if topic[2:26] != "0" * 24:
        return None
    return "0x" + topic[-40:]


def _signed(word: str, bits: int = 256) -> int:
    number = int(word, 16)
    return number - (1 << bits) if number >= (1 << (bits - 1)) else number


def decode_swap_event_candidate(log: dict) -> dict | None:
    """Return evidence only for a complete, shape-valid event; no guesswork."""
    topics = [_text_hex(item) for item in (log.get("topics") or [])]
    if not topics or topics[0] not in (V2_SWAP_TOPIC, V3_SWAP_TOPIC):
        return None
    emitter = str(log.get("address") or "").lower()
    if not HEX_ADDRESS.fullmatch(emitter) or len(topics) != 3:
        return None
    sender, recipient = _address_topic(topics[1]), _address_topic(topics[2])
    if not sender or not recipient:
        return None
    raw = _text_hex(log.get("data"))
    expected_words = 4 if topics[0] == V2_SWAP_TOPIC else 5
    if not raw.startswith("0x") or len(raw) != 2 + expected_words * 64:
        return None
    words = [raw[i:i + 64] for i in range(2, len(raw), 64)]
    if not all(HEX_WORD.fullmatch(word) for word in words):
        return None
    if topics[0] == V2_SWAP_TOPIC:
        fields = dict(zip(("amount0_in", "amount1_in", "amount0_out", "amount1_out"), (str(int(word, 16)) for word in words)))
        version = "v2_abi"
    else:
        fields = {
            "amount0_delta_raw": str(_signed(words[0])),
            "amount1_delta_raw": str(_signed(words[1])),
            "sqrt_price_x96_raw": str(int(words[2], 16)),
            "liquidity_raw": str(int(words[3], 16)),
            "tick": str(_signed(words[4][-6:], 24)),
        }
        if int(words[2], 16) >= 2**160 or int(words[3], 16) >= 2**128:
            return None
        # ABI int24 values must be sign extended across the 256-bit word.
        tick_value = _signed(words[4], 256)
        if tick_value < -(2**23) or tick_value >= 2**23:
            return None
        if int(words[4], 16) != (tick_value % (1 << 256)):
            return None
        fields["tick"] = str(tick_value)
        version = "v3_abi"
    return {
        "kind": "swap_event_candidate",
        "abi_shape": version,
        "emitter_contract": emitter,
        "sender": sender,
        "recipient": recipient,
        "raw_amounts": fields,
        "log_index": int(log.get("logIndex") or 0),
        "signature_and_shape_verified": True,
        "pool_identity_verified": False,
        "token0_verified": False,
        "token1_verified": False,
        "swap_confirmed": False,
        "note": "The log matches an established swap event ABI; emitting pool identity and token metadata are not verified.",
    }
