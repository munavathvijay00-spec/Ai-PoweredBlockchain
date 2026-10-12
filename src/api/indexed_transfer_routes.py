"""On-demand Alchemy address-indexed transfers with explicit per-direction limits.

Not a complete wallet history. No fabricated events, no provenance inference.
"""
import asyncio
import re

import aiohttp
from fastapi import APIRouter, HTTPException, Query
from src.utils.config import get_settings

router = APIRouter(prefix="/api/wallets", tags=["wallet intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def _transfer_page(session, rpc_url, address, direction, count, page_key=None):
    query = {
        "fromBlock": "0x0",
        "toBlock": "latest",
        direction: address,
        "category": ["external", "erc20"],
        "withMetadata": True,
        "excludeZeroValue": False,
        "maxCount": hex(count),
        "order": "desc",
    }
    if page_key:
        query["pageKey"] = page_key
    payload = {
        "jsonrpc": "2.0",
        "id": 1 if direction == "fromAddress" else 2,
        "method": "alchemy_getAssetTransfers",
        "params": [query],
    }
    async with session.post(rpc_url, json=payload) as response:
        if response.status != 200:
            raise HTTPException(status_code=502, detail="Upstream transfer provider unavailable")
        data = await response.json(content_type=None)
    if "error" in data:
        raise HTTPException(status_code=502, detail="Address-indexed transfer query rejected by provider")
    result = data.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("transfers"), list):
        raise HTTPException(status_code=502, detail="Unexpected transfer provider response")
    return result


@router.get("/{address}/transfers")
async def wallet_indexed_transfers(
    address: str,
    per_direction: int = Query(25, ge=1, le=50),
    outgoing_page_key: str | None = Query(None, min_length=1, max_length=2048),
    incoming_page_key: str | None = Query(None, min_length=1, max_length=2048),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    settings = get_settings()
    rpc_url = settings.ethereum_rpc_url
    if not rpc_url.startswith("https://") or "alchemy.com" not in rpc_url.split("/")[2].lower():
        raise HTTPException(status_code=503, detail="Alchemy mainnet RPC not configured")
    # Both directions are independently bounded; page keys reveal further results.
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            outgoing, incoming = await asyncio.gather(
                _transfer_page(session, rpc_url, address, "fromAddress", per_direction, outgoing_page_key),
                _transfer_page(session, rpc_url, address, "toAddress", per_direction, incoming_page_key),
            )
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise HTTPException(status_code=502, detail="Transfer provider timed out or failed")
    unique = {}
    for direction, result in (("outgoing", outgoing), ("incoming", incoming)):
        for transfer in result["transfers"]:
            # One transfer can appear in both directions for self-transfers.
            key = (transfer.get("uniqueId") or transfer.get("hash"), transfer.get("category"), transfer.get("from"), transfer.get("to"))
            if key not in unique:
                unique[key] = {
                    "hash": transfer.get("hash"),
                    "from_address": transfer.get("from"),
                    "to_address": transfer.get("to"),
                    "asset": transfer.get("asset"),
                    "category": transfer.get("category"),
                    "value": transfer.get("value"),
                    "block_number_hex": transfer.get("blockNum"),
                    "metadata": transfer.get("metadata"),
                    "direction": direction,
                    "evidence_url": "https://etherscan.io/tx/" + transfer["hash"] if transfer.get("hash") else None,
                }
    return {
        "address": address.lower(),
        "chain_id": 1,
        "provider": "alchemy_getAssetTransfers",
        "transfers": list(unique.values()),
        "returned": len(unique),
        "per_direction_limit": per_direction,
        "outgoing_next_page_key": outgoing.get("pageKey"),
        "incoming_next_page_key": incoming.get("pageKey"),
        "outgoing_has_more": bool(outgoing.get("pageKey")),
        "incoming_has_more": bool(incoming.get("pageKey")),
        "historical_completeness": False,
        "coverage": "Cursor-paginated newest-first external ETH and ERC-20 transfers. Request subsequent pages using returned per-direction page keys. Internal transfers, NFTs, and completeness beyond indexed categories are excluded.",
        "warning": "No matching transfers in this bounded query is not evidence of wallet inactivity.",
    }


@router.get("/{address}/indexed-graph")
async def wallet_indexed_graph(
    address: str,
    per_direction: int = Query(25, ge=1, le=50),
    outgoing_page_key: str | None = Query(None, min_length=1, max_length=2048),
    incoming_page_key: str | None = Query(None, min_length=1, max_length=2048),
):
    """One-hop, evidence-backed graph from the same Alchemy transfer source."""
    result = await wallet_indexed_transfers(
        address, per_direction, outgoing_page_key, incoming_page_key
    )
    root = address.lower()
    nodes = {root}
    edges = []
    for transfer in result["transfers"]:
        source = (transfer.get("from_address") or "").lower()
        target = (transfer.get("to_address") or "").lower()
        tx_hash = transfer.get("hash")
        if not ADDRESS.fullmatch(source) or not ADDRESS.fullmatch(target) or not tx_hash:
            continue
        nodes.update((source, target))
        edges.append({
            "source": source,
            "target": target,
            "tx_hash": tx_hash,
            "asset": transfer.get("asset"),
            "category": transfer.get("category"),
            "value": transfer.get("value"),
            "block_number_hex": transfer.get("block_number_hex"),
            "evidence_url": transfer.get("evidence_url"),
            "relationship": "indexed_transfer",
        })
    return {
        "root": root,
        "chain_id": 1,
        "depth": 1,
        "nodes": [{"id": item, "type": "address"} for item in sorted(nodes)],
        "edges": edges,
        "next_page_keys": {
            "outgoing": result["outgoing_next_page_key"],
            "incoming": result["incoming_next_page_key"],
        },
        "historical_completeness": False,
        "scope": result["coverage"],
        "provenance_warning": "Transfer edges establish recorded movements, not common ownership, laundering, beneficial ownership, or final destination.",
    }


@router.get("/{address}/investigation-report")
async def wallet_evidence_report(
    address: str,
    per_direction: int = Query(25, ge=1, le=50),
    outgoing_page_key: str | None = Query(None, min_length=1, max_length=2048),
    incoming_page_key: str | None = Query(None, min_length=1, max_length=2048),
):
    """Deterministic, source-linked investigation summary without unverified AI claims."""
    result = await wallet_indexed_transfers(
        address, per_direction, outgoing_page_key, incoming_page_key
    )
    root = address.lower()
    transfers = result["transfers"]
    incoming = [t for t in transfers if (t.get("to_address") or "").lower() == root]
    outgoing = [t for t in transfers if (t.get("from_address") or "").lower() == root]
    counterparties = {}
    for tx in transfers:
        src = (tx.get("from_address") or "").lower()
        dst = (tx.get("to_address") or "").lower()
        for other in (src, dst):
            if other != root and ADDRESS.fullmatch(other):
                item = counterparties.setdefault(other, {"address": other, "evidence_hashes": []})
                if tx.get("hash") and tx["hash"] not in item["evidence_hashes"]:
                    item["evidence_hashes"].append(tx["hash"])
    citations = []
    for tx in transfers:
        if tx.get("hash"):
            citations.append({
                "tx_hash": tx["hash"],
                "url": tx.get("evidence_url"),
                "category": tx.get("category"),
                "asset": tx.get("asset"),
            })
    return {
        "address": root,
        "chain_id": 1,
        "report_type": "deterministic_evidence_summary",
        "summary": (
            f"Observed {len(transfers)} unique indexed transfer records in the requested "
            f"pages, including {len(incoming)} incoming and {len(outgoing)} outgoing "
            "records (self-transfers count in both directions)."
        ),
        "observed_unique_transfers": len(transfers),
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
        "unique_counterparties": len(counterparties),
        "counterparties": sorted(counterparties.values(), key=lambda item: (-len(item["evidence_hashes"]), item["address"])),
        "evidence": citations,
        "pagination": {
            "outgoing_next_page_key": result["outgoing_next_page_key"],
            "incoming_next_page_key": result["incoming_next_page_key"],
        },
        "coverage": result["coverage"],
        "historical_completeness": False,
        "risk_assessment": {
            "status": "not_assessed",
            "reason": "Transfer counts and counterparties alone do not establish fraud, sanctions exposure, or illicit behavior.",
        },
        "limitations": [
            "This report covers only fetched pages and supported provider transfer categories.",
            "Evidence URLs are references to source transactions, not independent sanctions verification.",
            "No entity attribution, behavioral detection-quality claim, or multi-hop tracing is made.",
        ],
    }
