"""Bounded, deterministic decoding of standard Ethereum receipt logs.

No external metadata claims: symbols/decimals require a separate trusted lookup.
Unrecognized logs and malformed entries never become fabricated token transfers.
"""
from __future__ import annotations

from typing import Any

from web3 import Web3

TRANSFER = Web3.keccak(text="Transfer(address,address,uint256)").hex().lower()
APPROVAL = Web3.keccak(text="Approval(address,address,uint256)").hex().lower()
TRANSFER_SINGLE = Web3.keccak(text="TransferSingle(address,address,address,uint256,uint256)").hex().lower()
TRANSFER_BATCH = Web3.keccak(text="TransferBatch(address,address,address,uint256[],uint256[])").hex().lower()
SWAP_V2 = Web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex().lower()
ZERO = "0x" + "0" * 40


def _hex(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if hasattr(value, "hex") and not isinstance(value, str):
        s = value.hex()
        return s if s.startswith("0x") else "0x" + s
    return str(value)


def _address(topic: Any) -> str:
    raw = _hex(topic).lower().removeprefix("0x")
    if len(raw) != 64 or int(raw[:24], 16) != 0:
        raise ValueError("invalid indexed address")
    return "0x" + raw[24:]


def _word(data: str) -> int:
    raw = _hex(data).removeprefix("0x")
    if len(raw) != 64:
        raise ValueError("expected exactly one ABI word")
    return int(raw, 16)


def _contract(log: dict) -> str:
    addr = str(log["address"]).lower()
    if len(addr) != 42 or not addr.startswith("0x"):
        raise ValueError("invalid emitting contract")
    int(addr[2:], 16)
    return addr


def decode_log(log: dict) -> dict | None:
    """Decode a standard log without guessing token type or off-chain metadata."""
    topics = [_hex(t).lower() for t in log.get("topics", [])]
    if not topics:
        return None
    signature = topics[0]
    contract = _contract(log)
    data = _hex(log.get("data", "0x"))
    common = {
        "contract": contract,
        "log_index": int(log.get("logIndex", 0)),
        "tx_hash": _hex(log.get("transactionHash", "")),
        "source": "ethereum_receipt_log",
        "metadata_verified": False,
    }
    if signature == TRANSFER and len(topics) == 3:
        return {**common, "event": "transfer", "standard": "ERC20-compatible",
                "from_address": _address(topics[1]), "to_address": _address(topics[2]),
                "raw_amount": str(_word(data)), "symbol": None, "decimals": None}
    if signature == TRANSFER and len(topics) == 4 and data in ("0x", ""):
        return {**common, "event": "transfer", "standard": "ERC721-compatible",
                "from_address": _address(topics[1]), "to_address": _address(topics[2]),
                "token_id": str(int(topics[3], 16))}
    if signature == APPROVAL and len(topics) == 3:
        return {**common, "event": "approval", "standard": "ERC20-compatible",
                "owner": _address(topics[1]), "spender": _address(topics[2]),
                "raw_amount": str(_word(data)), "symbol": None, "decimals": None}
    if signature == APPROVAL and len(topics) == 4 and data in ("0x", ""):
        return {**common, "event": "approval", "standard": "ERC721-compatible",
                "owner": _address(topics[1]), "approved": _address(topics[2]),
                "token_id": str(int(topics[3], 16))}
    if signature == SWAP_V2 and len(topics) == 3:
        raw = data.removeprefix("0x")
        if len(raw) != 64 * 4:
            raise ValueError("invalid V2 swap payload")
        amounts = [str(int(raw[i:i + 64], 16)) for i in range(0, len(raw), 64)]
        return {**common, "event": "swap", "standard": "UniswapV2-compatible",
                "sender": _address(topics[1]), "to_address": _address(topics[2]),
                "amount0_in": amounts[0], "amount1_in": amounts[1],
                "amount0_out": amounts[2], "amount1_out": amounts[3],
                "protocol_verified": False}
    return None


def decode_receipt(receipt: dict, *, max_logs: int = 500) -> dict:
    """Decode bounded logs; report truncation and malformed logs explicitly."""
    if not 1 <= max_logs <= 1000:
        raise ValueError("max_logs must be between 1 and 1000")
    logs = receipt.get("logs") or []
    events = []
    invalid = 0
    for log in logs[:max_logs]:
        try:
            event = decode_log(log)
            if event is not None:
                events.append(event)
        except (ValueError, TypeError, KeyError, OverflowError):
            invalid += 1
    return {"tx_hash": _hex(receipt.get("transactionHash", "")),
            "status": int(receipt.get("status", 0)),
            "events": events, "decoded_count": len(events),
            "invalid_logs": invalid, "total_logs": len(logs),
            "truncated": len(logs) > max_logs,
            "note": "ERC-compatible event signatures do not establish contract authenticity or verified token metadata."}
