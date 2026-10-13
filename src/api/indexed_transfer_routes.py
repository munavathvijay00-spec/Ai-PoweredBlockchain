"""On-demand Alchemy address-indexed transfers with explicit per-direction limits.

Not a complete wallet history. No fabricated events, no provenance inference.
"""
import asyncio
import re
from urllib.parse import urlsplit

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
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
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Unexpected transfer provider response")
    if "error" in data:
        raise HTTPException(status_code=502, detail="Address-indexed transfer query rejected by provider")
    result = data.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("transfers"), list):
        raise HTTPException(status_code=502, detail="Unexpected transfer provider response")
    return result


async def _verified_entity_map(repo: TransactionRepository, addresses) -> dict:
    """Return only source-attributed entity rows already stored by ChainScope."""
    normalized = sorted({
        str(address).lower()
        for address in addresses
        if ADDRESS.fullmatch(str(address or ""))
    })
    if not normalized:
        return {}
    try:
        rows = await repo.db.fetch(
            """
            SELECT source, address, entity_id, entity_name, checked_at
            FROM verified_address_intelligence
            WHERE address = ANY($1::varchar[])
            ORDER BY address, source, entity_id
            """,
            normalized,
        )
    except Exception:
        # Entity context is enrichment only; investigation evidence must still work
        # if the optional intelligence table is unavailable during a migration.
        return {}

    entity_map = {}
    for row in rows:
        address = row["address"].lower()
        entity_map.setdefault(address, []).append({
            "source": row["source"],
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "checked_at": row["checked_at"].isoformat() if row["checked_at"] else None,
            "source_attributed": True,
        })
    return entity_map


@router.get("/{address}/transfers")
async def wallet_indexed_transfers(
    address: str,
    per_direction: int = Query(25, ge=1, le=50),
    outgoing_page_key: str | None = Query(None, min_length=1, max_length=2048),
    incoming_page_key: str | None = Query(None, min_length=1, max_length=2048),
    include_outgoing: bool = Query(True),
    include_incoming: bool = Query(True),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    if not include_outgoing and not include_incoming:
        raise HTTPException(status_code=422, detail="At least one transfer direction must be enabled")
    settings = get_settings()
    rpc_url = settings.ethereum_rpc_url
    parsed_rpc = urlsplit(rpc_url)
    hostname = (parsed_rpc.hostname or "").lower()
    if parsed_rpc.scheme != "https" or not (hostname == "alchemy.com" or hostname.endswith(".alchemy.com")):
        raise HTTPException(status_code=503, detail="Alchemy mainnet RPC not configured")
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            pending = {}
            if include_outgoing:
                pending["outgoing"] = _transfer_page(session, rpc_url, address, "fromAddress", per_direction, outgoing_page_key)
            if include_incoming:
                pending["incoming"] = _transfer_page(session, rpc_url, address, "toAddress", per_direction, incoming_page_key)
            pages = await asyncio.gather(*pending.values())
            page_results = dict(zip(pending.keys(), pages))
            outgoing = page_results.get("outgoing", {"transfers": [], "pageKey": None})
            incoming = page_results.get("incoming", {"transfers": [], "pageKey": None})
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise HTTPException(status_code=502, detail="Transfer provider timed out or failed")

    unique = {}
    for direction, result in (("outgoing", outgoing), ("incoming", incoming)):
        for transfer in result["transfers"]:
            key = (
                transfer.get("uniqueId") or transfer.get("hash"),
                transfer.get("category"), transfer.get("from"), transfer.get("to"),
            )
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
        "queried_directions": [direction for direction, enabled in (("outgoing", include_outgoing), ("incoming", include_incoming)) if enabled],
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
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """One-hop, evidence-backed graph enriched only with verified stored entity rows."""
    result = await wallet_indexed_transfers(
        address, per_direction, outgoing_page_key, incoming_page_key, True, True
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

    entity_map = await _verified_entity_map(repo, nodes)
    return {
        "root": root,
        "chain_id": 1,
        "depth": 1,
        "nodes": [
            {
                "id": item,
                "type": "address",
                "verified_entities": entity_map.get(item, []),
                "entity_context_status": "source_attributed_match" if entity_map.get(item) else "no_local_match",
            }
            for item in sorted(nodes)
        ],
        "edges": edges,
        "verified_entity_matches": sum(len(matches) for matches in entity_map.values()),
        "entity_context_note": "Only source-attributed records already stored in verified_address_intelligence are shown. No match does not establish anonymity, safety, or lack of attribution elsewhere.",
        "next_page_keys": {
            "outgoing": result["outgoing_next_page_key"],
            "incoming": result["incoming_next_page_key"],
        },
        "historical_completeness": False,
        "scope": result["coverage"],
        "provenance_warning": "Transfer edges establish recorded movements, not common ownership, laundering, beneficial ownership, or final destination.",
    }


def _observed_behavioral_signals(transfers, root):
    """Transparent heuristics over observed records; no criminality or ML claims."""
    signals = []

    def emit(code, title, evidence, explanation):
        hashes = sorted({t.get("hash") for t in evidence if t.get("hash")})
        if hashes:
            signals.append({
                "code": code,
                "title": title,
                "status": "review",
                "observed_count": len(evidence),
                "evidence": [{"tx_hash": h, "url": "https://etherscan.io/tx/" + h} for h in hashes[:20]],
                "explanation": explanation,
                "not_a_fraud_verdict": True,
            })

    pairs = {}
    for tx in transfers:
        sender = (tx.get("from_address") or "").lower()
        recipient = (tx.get("to_address") or "").lower()
        if ADDRESS.fullmatch(sender) and ADDRESS.fullmatch(recipient) and tx.get("hash"):
            pairs.setdefault((sender, recipient), []).append(tx)
    for _, group in sorted(pairs.items()):
        if len({t["hash"] for t in group}) >= 3:
            emit(
                "repeated_pair",
                "Repeated observed transfer pair",
                group,
                "Three or more distinct transaction hashes link the same sender and recipient in the fetched sample.",
            )

    self_transfers = [
        t for t in transfers
        if (t.get("from_address") or "").lower() == root
        and (t.get("to_address") or "").lower() == root
    ]
    if self_transfers:
        emit(
            "self_transfer",
            "Self-transfer observed",
            self_transfers,
            "The same address appears as sender and recipient. This can be ordinary wallet activity.",
        )
    return signals


@router.get("/{address}/investigation-report")
async def wallet_evidence_report(
    address: str,
    per_direction: int = Query(25, ge=1, le=50),
    outgoing_page_key: str | None = Query(None, min_length=1, max_length=2048),
    incoming_page_key: str | None = Query(None, min_length=1, max_length=2048),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Deterministic, source-linked investigation summary without unverified AI claims."""
    result = await wallet_indexed_transfers(
        address, per_direction, outgoing_page_key, incoming_page_key, True, True
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

    entity_map = await _verified_entity_map(repo, [root, *counterparties.keys()])
    for address_key, item in counterparties.items():
        item["verified_entities"] = entity_map.get(address_key, [])
        item["entity_context_status"] = "source_attributed_match" if entity_map.get(address_key) else "no_local_match"

    signals = _observed_behavioral_signals(transfers, root)
    citations = []
    for tx in transfers:
        if tx.get("hash"):
            citations.append({
                "tx_hash": tx["hash"],
                "url": tx.get("evidence_url"),
                "category": tx.get("category"),
                "asset": tx.get("asset"),
            })

    flattened_entity_matches = [
        {"address": address_key, **match}
        for address_key, matches in sorted(entity_map.items())
        for match in matches
    ]
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
        "verified_entity_intelligence": {
            "status": "matches_found" if flattened_entity_matches else "no_local_match",
            "matched_addresses": len(entity_map),
            "match_records": len(flattened_entity_matches),
            "investigated_address_matches": entity_map.get(root, []),
            "matches": flattened_entity_matches,
            "note": "These are source-attributed records stored by ChainScope. Absence of a local match is not evidence that an address is unassociated, unsanctioned, or safe.",
        },
        "evidence": citations,
        "behavioral_signals": signals,
        "detection_quality": {
            "status": "not_evaluated",
            "precision": None,
            "recall": None,
            "false_positive_rate": None,
            "reason": "No independently labeled evaluation set is available. Rules are review cues, not validated threat detection.",
        },
        "coverage_details": {
            "categories": ["external", "erc20"],
            "sort": "newest_first",
            "page_size_per_direction": per_direction,
            "outgoing_has_more": bool(result["outgoing_next_page_key"]),
            "incoming_has_more": bool(result["incoming_next_page_key"]),
            "complete_history": False,
            "entity_context": "source_attributed_local_matches_only",
        },
        "pagination": {
            "outgoing_next_page_key": result["outgoing_next_page_key"],
            "incoming_next_page_key": result["incoming_next_page_key"],
        },
        "coverage": result["coverage"],
        "historical_completeness": False,
        "risk_assessment": {
            "status": "not_assessed",
            "reason": "Transfer counts, behavioral rules, and entity labels alone do not establish fraud, sanctions exposure, or illicit behavior.",
        },
        "limitations": [
            "This report covers only fetched pages and supported provider transfer categories.",
            "Entity context is limited to source-attributed records already present in ChainScope's verified intelligence table.",
            "No local entity match does not establish that no attribution exists elsewhere.",
            "Evidence URLs are references to source transactions, not independent sanctions verification.",
            "Behavioral rules are transparent review cues, not evaluated detection models or fraud verdicts.",
            "No multi-hop tracing or beneficial-ownership inference is made.",
        ],
    }
