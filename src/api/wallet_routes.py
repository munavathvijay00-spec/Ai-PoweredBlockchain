"""Bounded, read-only wallet investigation from observed transactions."""
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from web3 import Web3

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/wallets", tags=["wallet intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


@router.get("/{address}")
async def wallet_profile(
    address: str,
    limit: int = Query(50, ge=1, le=100),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    address = address.lower()
    rows = await repo.db.fetch("""
        SELECT t.hash, t.block_number, t.timestamp, t.value::text AS value_wei,
               a_from.address AS from_address, a_to.address AS to_address
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE a_from.address = $1 OR a_to.address = $1
        ORDER BY t.block_number DESC, t.id DESC
        LIMIT $2
    """, address, limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    counterparties = {}
    for row in rows:
        other = row["to_address"] if row["from_address"] == address else row["from_address"]
        entry = counterparties.setdefault(other, {"address": other, "observed_transactions": 0, "evidence_tx_hashes": []})
        entry["observed_transactions"] += 1
        if len(entry["evidence_tx_hashes"]) < 5:
            entry["evidence_tx_hashes"].append(row["hash"])
    return {
        "address": address,
        "observed_transactions": len(rows),
        "timeline": [dict(r) for r in rows],
        "counterparties": sorted(counterparties.values(), key=lambda x: -x["observed_transactions"]),
        "truncated": truncated,
        "scope": "Only transactions stored by this platform; not full Ethereum wallet history. Current ingestion deletes transactions older than 30 minutes.",
        "historical_completeness": False,
        "coverage_url": "/api/coverage",
        "token_activity": {"status": "not_indexed", "note": "Token logs are decoded on demand, not persisted."},
    }


@router.get("/{address}/balance")
async def wallet_live_balance(address: str):
    """Live native ETH balance pinned to one Ethereum mainnet block."""
    from src.blockchain.client import BlockchainClient

    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")

    normalized_address = address.lower()
    checksum_address = Web3.to_checksum_address(normalized_address)
    client = BlockchainClient()
    try:
        if not await client.connect():
            raise HTTPException(status_code=503, detail="Ethereum mainnet RPC unavailable")

        # Pin the balance to an explicit block so the displayed value is reproducible.
        block_number = await client.get_latest_block_number()
        balance_wei = await client.w3.eth.get_balance(
            checksum_address,
            block_identifier=block_number,
        )
        return {
            "address": normalized_address,
            "chain_id": 1,
            "block_number": block_number,
            "balance_wei": str(balance_wei),
            "balance_eth": str(Decimal(balance_wei) / Decimal(10**18)),
            "source": "configured_ethereum_mainnet_rpc",
            "historical_completeness": False,
            "note": "Point-in-time native ETH balance. Does not include ERC-20 balances or prove complete wallet transaction history.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Wallet balance lookup failed address={} error_type={}",
            normalized_address,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Could not retrieve verified Ethereum balance") from exc
    finally:
        await client.close()


@router.get("/tx/{tx_hash}/receipt-evidence")
async def transaction_receipt_evidence(tx_hash: str):
    """Read-only mainnet transaction evidence pinned to its confirmed receipt."""
    from src.blockchain.client import BlockchainClient
    from src.risk.receipt_semantics import HASH, decode_receipt_evidence

    if not HASH.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail="Invalid Ethereum transaction hash")

    client = BlockchainClient()
    try:
        if not await client.connect():
            raise HTTPException(status_code=503, detail="Ethereum mainnet RPC unavailable")
        transaction = await client.w3.eth.get_transaction(tx_hash)
        receipt = await client.w3.eth.get_transaction_receipt(tx_hash)
        return decode_receipt_evidence(tx_hash, dict(transaction), dict(receipt))
    except HTTPException:
        raise
    except Exception as exc:
        kind = type(exc).__name__
        logger.warning("Receipt evidence lookup failed error_type={}", kind)
        if kind in {"TransactionNotFound", "TransactionNotFoundError"}:
            raise HTTPException(status_code=404, detail="Transaction receipt not found") from exc
        raise HTTPException(status_code=502, detail="Verified transaction receipt unavailable") from exc
    finally:
        await client.close()
