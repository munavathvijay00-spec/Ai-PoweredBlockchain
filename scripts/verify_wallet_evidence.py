"""Offline structural verifier for ChainScope wallet evidence exports.

Usage: python scripts/verify_wallet_evidence.py evidence.json
Checks consistency and hash/link syntax, NOT on-chain authenticity.
"""
import json
import re
import sys
from pathlib import Path

ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
HASH = re.compile(r"^0x[a-fA-F0-9]{64}$")


def transfer_key(tx):
    return tuple(str(tx.get(k, "")) for k in (
        "hash", "from_address", "to_address", "category", "asset",
        "block_number_hex", "value",
    ))


def verify(bundle):
    errors = []
    if bundle.get("schema_version") != "chainscope-wallet-evidence-v1":
        errors.append("Unsupported evidence schema version")
    if bundle.get("chain") != "ethereum-mainnet":
        errors.append("Unexpected chain")
    wallet = bundle.get("investigated_address", "")
    if not isinstance(wallet, str) or not ADDRESS.fullmatch(wallet):
        errors.append("Invalid investigated address")
        wallet = ""
    transfers = bundle.get("transfers")
    if not isinstance(transfers, list):
        errors.append("Transfers must be a list")
        transfers = []
    keys = set()
    hashes = set()
    for i, tx in enumerate(transfers):
        if not isinstance(tx, dict):
            errors.append(f"Transfer {i} is not an object")
            continue
        sender = str(tx.get("from_address") or "").lower()
        recipient = str(tx.get("to_address") or "").lower()
        if wallet and wallet.lower() not in (sender, recipient):
            errors.append(f"Transfer {i} is unrelated to investigated wallet")
        key = transfer_key(tx)
        if key in keys:
            errors.append(f"Duplicate transfer at index {i}")
        keys.add(key)
        tx_hash = tx.get("hash")
        if isinstance(tx_hash, str) and HASH.fullmatch(tx_hash):
            hashes.add(tx_hash.lower())
        else:
            errors.append(f"Transfer {i} has no valid transaction hash")
    coverage = bundle.get("coverage") or {}
    if not isinstance(coverage, dict) or coverage.get("transfer_records_loaded") != len(transfers):
        errors.append("Coverage transfer count does not match evidence")
    links = bundle.get("evidence_links")
    if not isinstance(links, list):
        errors.append("Evidence links must be a list")
        links = []
    link_hashes = set()
    for i, item in enumerate(links):
        if not isinstance(item, dict):
            errors.append(f"Evidence link {i} is not an object")
            continue
        tx_hash = item.get("tx_hash")
        if not isinstance(tx_hash, str) or not HASH.fullmatch(tx_hash):
            errors.append(f"Evidence link {i} has invalid hash")
            continue
        if item.get("explorer_url") != "https://etherscan.io/tx/" + tx_hash:
            errors.append(f"Evidence link {i} has mismatched URL")
        if tx_hash.lower() in link_hashes:
            errors.append(f"Duplicate evidence link {i}")
        link_hashes.add(tx_hash.lower())
    if hashes != link_hashes:
        errors.append("Evidence links do not exactly cover valid transfer hashes")
    return {
        "status": "structurally_consistent" if not errors else "invalid",
        "wallet": wallet,
        "transfer_records": len(transfers),
        "unique_transaction_hashes": len(hashes),
        "errors": errors,
        "warning": "This checks exported data consistency only; it does not verify Ethereum receipts, chain state, data completeness, or wallet identity.",
    }


def main(path):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        raise ValueError("Evidence bundle must be a JSON object")
    result = verify(bundle)
    print(json.dumps(result, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else 2)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
