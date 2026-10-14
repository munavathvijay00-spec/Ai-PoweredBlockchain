"""Persistent sparse wallet-history cache backed by Alchemy transfers.

ChainScope does not warehouse Ethereum history in the free-tier database. It
stores normalized evidence for investigated wallets under strict row budgets;
older cache entries can always be re-fetched from the provider on demand.
"""
import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime

import aiohttp
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.api.indexed_transfer_routes import _transfer_page, _selected_categories
from src.database.repositories import TransactionRepository
from src.metrics import historical_provider_requests_total
from src.storage_budget import (
    HISTORY_MAX_ROWS_GLOBAL,
    HISTORY_MAX_ROWS_PER_WALLET,
    HISTORY_MAX_WALLETS,
    prune_historical_evidence,
)
from src.utils.config import get_settings

router = APIRouter(prefix="/api/wallets", tags=["historical wallet evidence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_INVALID_PROVIDER_KEYS = {"", "not-set", "unused", "dummy", "dummy_key_for_ci"}


async def require_history_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


def _alchemy_rpc_url(settings) -> str | None:
    key = (settings.alchemy_api_key or "").strip()
    if key.lower() in _INVALID_PROVIDER_KEYS:
        return None
    return f"https://eth-mainnet.g.alchemy.com/v2/{key}"


def _evidence_key(transfer: dict, direction: str) -> str:
    provider_id = transfer.get("uniqueId")
    if provider_id:
        return f"alchemy:{provider_id}"
    stable = json.dumps({
        "hash": transfer.get("hash"),
        "category": transfer.get("category"),
        "from": transfer.get("from"),
        "to": transfer.get("to"),
        "token_id": transfer.get("tokenId") or transfer.get("erc721TokenId"),
        "erc1155": transfer.get("erc1155Metadata"),
        "raw_contract": transfer.get("rawContract"),
        "value": transfer.get("value"),
        "direction": direction,
        "block": transfer.get("blockNum"),
    }, sort_keys=True, separators=(",", ":"), default=str)
    return "alchemy:fallback:" + hashlib.sha256(stable.encode()).hexdigest()


def _block_number(value):
    if value is None:
        return None
    try:
        return int(str(value), 16) if str(value).startswith("0x") else int(value)
    except (TypeError, ValueError):
        return None


def _block_timestamp(transfer: dict):
    metadata = transfer.get("metadata") or {}
    value = metadata.get("blockTimestamp") if isinstance(metadata, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _contract_address(transfer: dict):
    raw = transfer.get("rawContract") or {}
    value = raw.get("address") if isinstance(raw, dict) else None
    if value and ADDRESS.fullmatch(str(value)):
        return str(value).lower()
    return None


async def _require_schema(repo: TransactionRepository):
    exists = await repo.db.fetchval(
        "SELECT to_regclass('wallet_transfer_evidence') IS NOT NULL"
    )
    if not exists:
        raise HTTPException(
            status_code=503,
            detail="Historical evidence schema not initialized; apply scripts/intelligence_v2.sql",
        )


async def _save_page(repo, wallet: str, direction: str, transfers: list[dict]) -> int:
    """Persist compact normalized evidence, not the provider's full JSON payload."""
    inserted = 0
    async with repo.db.transaction():
        for transfer in transfers:
            tx_hash = transfer.get("hash")
            source = (transfer.get("from") or "").lower() or None
            target = (transfer.get("to") or "").lower() or None
            token_id = transfer.get("tokenId") or transfer.get("erc721TokenId")
            key = _evidence_key(transfer, direction)
            result = await repo.db.execute(
                """
                INSERT INTO wallet_transfer_evidence (
                    chain_id, wallet_address, evidence_key, provider,
                    provider_unique_id, tx_hash, category, direction,
                    from_address, to_address, asset, value_text, token_id,
                    contract_address, block_number, block_timestamp,
                    raw_evidence, evidence_url, observed_at
                ) VALUES (
                    1, $1, $2, 'alchemy_getAssetTransfers',
                    $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14, '{}'::jsonb, $15, NOW()
                )
                ON CONFLICT (chain_id, wallet_address, evidence_key) DO NOTHING
                """,
                wallet,
                key,
                transfer.get("uniqueId"),
                tx_hash,
                transfer.get("category") or "unknown",
                direction,
                source,
                target,
                transfer.get("asset"),
                None if transfer.get("value") is None else str(transfer.get("value")),
                None if token_id is None else str(token_id),
                _contract_address(transfer),
                _block_number(transfer.get("blockNum")),
                _block_timestamp(transfer),
                f"https://etherscan.io/tx/{tx_hash}" if tx_hash else None,
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def _wallet_bounds(repo: TransactionRepository, wallet: str):
    return await repo.db.fetchrow(
        """SELECT COUNT(*) AS count, MIN(block_number) AS oldest, MAX(block_number) AS newest
           FROM wallet_transfer_evidence WHERE chain_id=1 AND wallet_address=$1""",
        wallet,
    )


@router.post("/{address}/history/sync", dependencies=[Depends(require_history_key)])
async def sync_wallet_history(
    address: str,
    pages: int = Query(2, ge=1, le=5),
    per_direction: int = Query(50, ge=1, le=50),
    include_internal: bool = Query(True),
    include_nfts: bool = Query(True),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    await _require_schema(repo)
    wallet = address.lower()
    categories = _selected_categories(include_internal, include_nfts)
    settings = get_settings()
    provider_url = _alchemy_rpc_url(settings)
    if not provider_url:
        raise HTTPException(
            status_code=503,
            detail="Alchemy historical provider is not configured",
        )

    state = await repo.db.fetchrow(
        """SELECT outgoing_page_key, incoming_page_key, outgoing_complete, incoming_complete
           FROM wallet_history_sync
           WHERE chain_id=1 AND wallet_address=$1 AND provider='alchemy_getAssetTransfers'""",
        wallet,
    )
    outgoing_key = state.get("outgoing_page_key") if state else None
    incoming_key = state.get("incoming_page_key") if state else None
    outgoing_complete = bool(state and state.get("outgoing_complete"))
    incoming_complete = bool(state and state.get("incoming_complete"))

    fetched = 0
    inserted = 0
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for _ in range(pages):
                if outgoing_complete and incoming_complete:
                    break
                calls = []
                names = []
                if not outgoing_complete:
                    names.append("outgoing")
                    calls.append(_transfer_page(
                        session, provider_url, wallet, "fromAddress",
                        per_direction, outgoing_key, categories,
                    ))
                if not incoming_complete:
                    names.append("incoming")
                    calls.append(_transfer_page(
                        session, provider_url, wallet, "toAddress",
                        per_direction, incoming_key, categories,
                    ))
                results = await asyncio.gather(*calls)
                for name, result in zip(names, results):
                    historical_provider_requests_total.labels(
                        provider="alchemy_getAssetTransfers", status="success"
                    ).inc()
                    records = result.get("transfers", [])
                    fetched += len(records)
                    inserted += await _save_page(repo, wallet, name, records)
                    next_key = result.get("pageKey")
                    if name == "outgoing":
                        outgoing_key = next_key
                        outgoing_complete = not bool(next_key)
                    else:
                        incoming_key = next_key
                        incoming_complete = not bool(next_key)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        historical_provider_requests_total.labels(
            provider="alchemy_getAssetTransfers", status="error"
        ).inc()
        raise HTTPException(status_code=502, detail="Historical transfer provider failed")

    bounds = await _wallet_bounds(repo, wallet)
    await repo.db.execute(
        """
        INSERT INTO wallet_history_sync (
            chain_id, wallet_address, provider, categories,
            outgoing_page_key, incoming_page_key, outgoing_complete,
            incoming_complete, newest_block, oldest_block, records_cached,
            last_error, updated_at
        ) VALUES (1,$1,'alchemy_getAssetTransfers',$2::jsonb,$3,$4,$5,$6,$7,$8,$9,NULL,NOW())
        ON CONFLICT (chain_id, wallet_address, provider) DO UPDATE SET
            categories=EXCLUDED.categories,
            outgoing_page_key=EXCLUDED.outgoing_page_key,
            incoming_page_key=EXCLUDED.incoming_page_key,
            outgoing_complete=EXCLUDED.outgoing_complete,
            incoming_complete=EXCLUDED.incoming_complete,
            newest_block=EXCLUDED.newest_block,
            oldest_block=EXCLUDED.oldest_block,
            records_cached=EXCLUDED.records_cached,
            last_error=NULL,
            updated_at=NOW()
        """,
        wallet, json.dumps(categories), outgoing_key, incoming_key,
        outgoing_complete, incoming_complete,
        bounds.get("newest"), bounds.get("oldest"), int(bounds.get("count") or 0),
    )

    pruning = await prune_historical_evidence(repo.db, wallet)
    pruned = pruning["wallet_deleted"] + pruning["evicted_rows"]
    if pruning["wallet_deleted"]:
        outgoing_complete = False
        incoming_complete = False
    bounds = await _wallet_bounds(repo, wallet)

    current_sync = await repo.db.fetchrow(
        """
        SELECT outgoing_complete, incoming_complete
        FROM wallet_history_sync
        WHERE chain_id=1 AND wallet_address=$1 AND provider='alchemy_getAssetTransfers'
        """,
        wallet,
    )
    if current_sync:
        outgoing_complete = bool(current_sync.get("outgoing_complete"))
        incoming_complete = bool(current_sync.get("incoming_complete"))

    await repo.db.execute(
        """
        UPDATE wallet_history_sync
        SET newest_block=$2,
            oldest_block=$3,
            records_cached=$4,
            updated_at=NOW()
        WHERE chain_id=1 AND wallet_address=$1 AND provider='alchemy_getAssetTransfers'
        """,
        wallet,
        bounds.get("newest"),
        bounds.get("oldest"),
        int(bounds.get("count") or 0),
    )

    return {
        "address": wallet,
        "provider": "alchemy_getAssetTransfers",
        "fetched_this_request": fetched,
        "new_records_cached": inserted,
        "records_cached": int(bounds.get("count") or 0),
        "oldest_block_cached": bounds.get("oldest"),
        "newest_block_cached": bounds.get("newest"),
        "outgoing_complete": outgoing_complete,
        "incoming_complete": incoming_complete,
        "historical_complete_for_selected_categories": outgoing_complete and incoming_complete,
        "categories": categories,
        "cache_pruned_this_request": pruned,
        "cache_evicted_wallets_this_request": pruning["evicted_wallets"],
        "cache_policy": {
            "max_rows_per_wallet": HISTORY_MAX_ROWS_PER_WALLET,
            "max_wallets": HISTORY_MAX_WALLETS,
            "max_rows_global": HISTORY_MAX_ROWS_GLOBAL,
            "raw_provider_payloads_stored": False,
            "refetchable": True,
        },
        "warning": "Provider history is deeper than the local cache. Completeness applies only while selected-category pagination is complete and no rows for this wallet were evicted; this is not full EVM execution tracing.",
    }


@router.get("/{address}/history")
async def cached_wallet_history(
    address: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    await _require_schema(repo)
    wallet = address.lower()
    rows = await repo.db.fetch(
        """SELECT evidence_key, provider_unique_id, tx_hash, category, direction,
                  from_address, to_address, asset, value_text, token_id,
                  contract_address, block_number, block_timestamp, evidence_url
           FROM wallet_transfer_evidence
           WHERE chain_id=1 AND wallet_address=$1
           ORDER BY block_number DESC NULLS LAST, observed_at DESC
           LIMIT $2 OFFSET $3""",
        wallet, limit, offset,
    )
    total = int(await repo.db.fetchval(
        "SELECT COUNT(*) FROM wallet_transfer_evidence WHERE chain_id=1 AND wallet_address=$1",
        wallet,
    ))
    sync = await repo.db.fetchrow(
        """SELECT provider, categories, outgoing_complete, incoming_complete,
                  oldest_block, newest_block, records_cached, updated_at
           FROM wallet_history_sync WHERE chain_id=1 AND wallet_address=$1
           ORDER BY updated_at DESC LIMIT 1""",
        wallet,
    )
    return {
        "address": wallet,
        "records": rows,
        "total_cached": total,
        "limit": limit,
        "offset": offset,
        "sync": sync,
        "historical_complete_for_selected_categories": bool(
            sync and sync.get("outgoing_complete") and sync.get("incoming_complete")
        ),
        "cache_policy": {
            "max_rows_per_wallet": HISTORY_MAX_ROWS_PER_WALLET,
            "max_wallets": HISTORY_MAX_WALLETS,
            "max_rows_global": HISTORY_MAX_ROWS_GLOBAL,
            "raw_provider_payloads_stored": False,
            "refetchable": True,
        },
        "warning": "This is a bounded persistent cache of investigated-wallet evidence. Deeper provider history is fetched on demand; the local database is not an Ethereum archive.",
    }
