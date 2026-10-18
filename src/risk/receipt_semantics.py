"""Reconstruct only observations supported by a real Ethereum transaction receipt.

A successful receipt proves inclusion/execution status and emitted event logs, but
does not by itself prove economic intent, beneficial ownership, swaps or bridges.
"""
from __future__ import annotations

import re
from src.risk.tx_semantics import selector_candidate

HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC20_APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f714fef7b7e10ac6a81914f2af1df4d7c3b9259a8cce4"


def _hex(value) -> str:
    if isinstance(value, str):
        return value.lower()
    if hasattr(value, "hex"):
        result = value.hex()
        return ("0x" + result if not result.startswith("0x") else result).lower()
    return ""


def decode_receipt_evidence(tx_hash: str, transaction, receipt) -> dict:
    """Decode only indexed ERC-20-style Transfer and Approval events.

    An event has the same signature on ERC-721; Transfer only counts as ERC-20
    value if three topics are present (topic0 + sender + receiver). ERC-721 has
    four indexed topics (tokenId included) and is not decoded as fungible.
    """
    if not HASH.fullmatch(tx_hash):
        raise ValueError("Invalid Ethereum tx hash")
    status = receipt.get("status")
    success = status == 1 if status is not None else None
    events = []
    skipped = 0
    logs = receipt.get("logs") or []
    for log in logs[:2000]:
        topics = [_hex(value) for value in (log.get("topics") or [])]
        first = topics[0] if topics else ""
        if first not in (ERC20_TRANSFER_TOPIC, ERC20_APPROVAL_TOPIC):
            continue
        if len(topics) != 3:
            skipped += 1
            continue
        raw = _hex(log.get("data"))
        if not re.fullmatch(r"0x[0-9a-f]{64}", raw):
            skipped += 1
            continue
        address = str(log.get("address") or "").lower()
        if not re.fullmatch(r"0x[0-9a-f]{40}", address):
            skipped += 1
            continue
        events.append({
            "kind": "erc20_transfer_candidate" if first == ERC20_TRANSFER_TOPIC else "erc20_approval_candidate",
            "emitter_contract": address,
            "from_or_owner": "0x" + topics[1][-40:],
            "to_or_spender": "0x" + topics[2][-40:],
            "raw_uint256": str(int(raw, 16)),
            "log_index": int(log.get("logIndex", 0) or 0),
            "event_signature_verified": True,
            "token_standard_verified": False,
            "note": "Standard ABI event signature and indexed topic structure; token contract and decimals not independently verified.",
        })

    input_data = _hex(transaction.get("input"))
    method = selector_candidate(input_data)
    return {
        "schema_version": "chainscope.receipt-semantics.v1",
        "chain_id": 1,
        "tx_hash": tx_hash.lower(),
        "evidence_url": "https://etherscan.io/tx/" + tx_hash.lower(),
        "receipt_available": True,
        "receipt_status": "success" if success is True else "reverted" if success is False else "unknown",
        "block_number": int(receipt.get("blockNumber") or 0),
        "transaction_from": str(transaction.get("from") or "").lower(),
        "transaction_to": str(transaction.get("to") or "").lower() if transaction.get("to") else None,
        "native_value_wei": str(int(transaction.get("value") or 0)),
        "gas_used": str(int(receipt.get("gasUsed") or 0)),
        "method_selector": method,
        "decoded_event_candidates": events,
        "skipped_ambiguous_events": skipped,
        "logs_examined": min(len(logs), 2000),
        "logs_truncated": len(logs) > 2000,
        "swap_confirmed": False,
        "bridge_confirmed": False,
        "internal_transfers_complete": False,
        "coverage": "Live RPC transaction and receipt only; no full EVM trace or independently verified token ABI metadata.",
        "interpretation": "Receipt status and emitted event evidence, not a verified economic swap or bridge reconstruction.",
    }
