"""Bounded native and token fund-flow investigation primitives."""
from collections import Counter, defaultdict, deque
from decimal import Decimal, InvalidOperation
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.risk.tx_semantics import summarize_transfer_semantics

router = APIRouter(prefix="/api/wallets", tags=["wallet intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _decimal_amount(value) -> Decimal | None:
    """Parse provider human-readable token values without accepting NaN/negative values."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _edge(row: dict, hop: int) -> dict:
    source = str(row["from_address"]).lower()
    target = str(row["to_address"]).lower()
    return {
        "source": source,
        "target": target,
        "tx_hash": row["hash"],
        "block_number": int(row["block_number"] or 0),
        "value_wei": str(row["value_wei"]),
        "risk_score": int(row.get("risk_score") or 0),
        "hop": hop,
        "asset": "ETH",
        "chain_id": 1,
        "evidence_url": "https://etherscan.io/tx/" + row["hash"],
        "relationship": "observed_native_transaction",
    }


def _motifs(edges: list[dict]) -> dict:
    outgoing = Counter(edge["source"] for edge in edges)
    incoming = Counter(edge["target"] for edge in edges)
    adjacency = defaultdict(set)
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
    reciprocal = []
    seen_pairs = set()
    for source, targets in adjacency.items():
        for target in targets:
            key = tuple(sorted((source, target)))
            if key in seen_pairs:
                continue
            if source in adjacency.get(target, set()):
                reciprocal.append({"a": key[0], "b": key[1]})
                seen_pairs.add(key)
    return {
        "fan_out": [{"address": a, "edge_count": c} for a, c in outgoing.most_common(10) if c >= 3],
        "fan_in": [{"address": a, "edge_count": c} for a, c in incoming.most_common(10) if c >= 3],
        "reciprocal_pairs": reciprocal[:20],
        "note": "Motifs describe observed retained transfers only and are not fraud verdicts.",
    }


def _directed_paths(root: str, edges: list[dict], max_depth: int, max_paths: int = 30) -> list[dict]:
    by_source = defaultdict(list)
    for edge in edges:
        by_source[edge["source"]].append(edge)
    paths = []
    queue = deque([(root, [], {root})])
    while queue and len(paths) < max_paths:
        node, path, seen = queue.popleft()
        if len(path) >= max_depth:
            continue
        for edge in by_source.get(node, []):
            target = edge["target"]
            next_path = path + [edge]
            paths.append({
                "hop_count": len(next_path),
                "addresses": [root] + [item["target"] for item in next_path],
                "tx_hashes": [item["tx_hash"] for item in next_path],
                "edge_values_wei": [item["value_wei"] for item in next_path],
                "path_min_value_wei": str(min(int(item["value_wei"]) for item in next_path)),
                "path_sum_value_wei": str(sum(int(item["value_wei"]) for item in next_path)),
                "max_risk_score": max(int(item.get("risk_score") or 0) for item in next_path),
                "relationship": "observed_directed_path",
            })
            if target not in seen:
                queue.append((target, next_path, seen | {target}))
            if len(paths) >= max_paths:
                break
    return paths


async def _fetch_hop(repo: TransactionRepository, frontier: list[str], per_hop_limit: int):
    return await repo.db.fetch("""
        SELECT t.hash, t.block_number, t.value::text AS value_wei, t.risk_score,
               a_from.address AS from_address, a_to.address AS to_address
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE a_from.address = ANY($1::text[]) OR a_to.address = ANY($1::text[])
        ORDER BY t.block_number DESC, t.id DESC
        LIMIT $2
    """, frontier, per_hop_limit + 1)


async def _build_graph(repo: TransactionRepository, root: str, limit: int, depth: int, per_hop_limit: int):
    visited = {root}
    frontier = [root]
    raw_edges = []
    seen_hashes = set()
    truncated = False
    hop_stats = []
    for hop in range(1, depth + 1):
        if not frontier or len(raw_edges) >= limit:
            break
        cap = min(per_hop_limit, limit - len(raw_edges))
        rows = await _fetch_hop(repo, frontier, cap)
        if len(rows) > cap:
            truncated = True
            rows = rows[:cap]
        next_frontier = set()
        added = 0
        for row in rows:
            if row["hash"] in seen_hashes:
                continue
            seen_hashes.add(row["hash"])
            item = _edge(dict(row), hop)
            raw_edges.append(item)
            added += 1
            for node in (item["source"], item["target"]):
                if node not in visited:
                    next_frontier.add(node)
                    visited.add(node)
            if len(raw_edges) >= limit:
                truncated = True
                break
        hop_stats.append({"hop": hop, "frontier_addresses": len(frontier), "edges_added": added, "new_addresses": len(next_frontier)})
        frontier = sorted(next_frontier)
    return visited, raw_edges, truncated, hop_stats


def _categories_include_erc20(value) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(str(item).lower() == "erc20" for item in value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            return any(str(item).lower() == "erc20" for item in parsed)
        return "erc20" in value.lower()
    return False


async def _token_flow_from_cache(repo: TransactionRepository, root: str, limit: int = 2000) -> dict:
    """Summarize one-hop cached ERC-20 evidence without asserting multi-hop conservation."""
    table_exists = await repo.db.fetchval("SELECT to_regclass('public.wallet_transfer_evidence') IS NOT NULL")
    if not table_exists:
        return {
            "available": False,
            "records_examined": 0,
            "assets": [],
            "edges": [],
            "coverage": {"selected_category_history_complete": False, "reason": "wallet_transfer_evidence_unavailable"},
            "scope": "No provider-indexed ERC-20 cache is currently available.",
        }

    rows = await repo.db.fetch("""
        SELECT evidence_key,tx_hash,category,direction,from_address,to_address,asset,
               value_text,token_id,contract_address,block_number,block_timestamp,evidence_url
        FROM wallet_transfer_evidence
        WHERE chain_id=1
          AND category='erc20'
          AND (wallet_address=$1 OR from_address=$1 OR to_address=$1)
        ORDER BY block_number DESC NULLS LAST
        LIMIT $2
    """, root, limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]

    deduped = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        key = row.get("evidence_key") or (
            row.get("tx_hash"), row.get("from_address"), row.get("to_address"),
            row.get("contract_address"), row.get("value_text"), row.get("token_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        source = str(row.get("from_address") or "").lower()
        target = str(row.get("to_address") or "").lower()
        if source != root and target != root:
            continue
        if not ADDRESS.fullmatch(source) or not ADDRESS.fullmatch(target):
            continue
        row["from_address"] = source
        row["to_address"] = target
        contract = str(row.get("contract_address") or "").lower()
        row["contract_address"] = contract if ADDRESS.fullmatch(contract) else None
        deduped.append(row)

    contracts = sorted({row["contract_address"] for row in deduped if row.get("contract_address")})
    labels_by_contract = defaultdict(list)
    if contracts:
        try:
            labels = await repo.db.fetch("""
                SELECT address,source,entity_id,entity_name,entity_type,confidence,source_url,verified_at
                FROM entity_attributions
                WHERE chain_id=1 AND address=ANY($1::text[])
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC,verified_at DESC
            """, contracts)
            for label in labels:
                item = dict(label)
                labels_by_contract[str(item["address"]).lower()].append(item)
        except Exception:
            labels_by_contract = defaultdict(list)

    aggregate = defaultdict(lambda: {
        "incoming_amount": Decimal("0"), "outgoing_amount": Decimal("0"),
        "incoming_transfer_count": 0, "outgoing_transfer_count": 0,
        "evidence_hashes": set(), "counterparties": set(),
    })
    edges = []
    for row in deduped:
        source = row["from_address"]
        target = row["to_address"]
        amount = _decimal_amount(row.get("value_text"))
        asset = str(row.get("asset") or "UNKNOWN").strip() or "UNKNOWN"
        contract = row.get("contract_address")
        asset_key = (contract or "", asset.upper())
        stats = aggregate[asset_key]
        tx_hash = row.get("tx_hash")
        if source == root:
            stats["outgoing_transfer_count"] += 1
            stats["counterparties"].add(target)
            if amount is not None:
                stats["outgoing_amount"] += amount
            direction = "outgoing"
        else:
            stats["incoming_transfer_count"] += 1
            stats["counterparties"].add(source)
            if amount is not None:
                stats["incoming_amount"] += amount
            direction = "incoming"
        if tx_hash:
            stats["evidence_hashes"].add(tx_hash)
        edges.append({
            "source": source,
            "target": target,
            "tx_hash": tx_hash,
            "asset": asset,
            "category": "erc20",
            "contract_address": contract,
            "value": _decimal_text(amount) if amount is not None else None,
            "direction_from_root": direction,
            "block_number": row.get("block_number"),
            "block_timestamp": row.get("block_timestamp"),
            "evidence_url": row.get("evidence_url") or (f"https://etherscan.io/tx/{tx_hash}" if tx_hash else None),
            "verified_contract_labels": labels_by_contract.get(contract, []) if contract else [],
            "relationship": "provider_indexed_erc20_transfer",
        })

    assets = []
    for (contract, asset), stats in aggregate.items():
        incoming_amount = stats["incoming_amount"]
        outgoing_amount = stats["outgoing_amount"]
        labels = labels_by_contract.get(contract, []) if contract else []
        assets.append({
            "asset": asset,
            "contract_address": contract or None,
            "incoming_amount": _decimal_text(incoming_amount),
            "outgoing_amount": _decimal_text(outgoing_amount),
            "net_amount": _decimal_text(incoming_amount - outgoing_amount),
            "incoming_transfer_count": stats["incoming_transfer_count"],
            "outgoing_transfer_count": stats["outgoing_transfer_count"],
            "unique_counterparties": len(stats["counterparties"]),
            "evidence_transaction_count": len(stats["evidence_hashes"]),
            "verified_contract_labels": labels,
            "source_attributed_asset": bool(labels),
        })
    assets.sort(key=lambda item: item["incoming_transfer_count"] + item["outgoing_transfer_count"], reverse=True)

    sync = None
    sync_exists = await repo.db.fetchval("SELECT to_regclass('public.wallet_history_sync') IS NOT NULL")
    if sync_exists:
        sync_row = await repo.db.fetchrow("""
            SELECT provider,categories,outgoing_complete,incoming_complete,oldest_block,newest_block,
                   records_cached,updated_at,last_error
            FROM wallet_history_sync
            WHERE chain_id=1 AND wallet_address=$1
            ORDER BY updated_at DESC LIMIT 1
        """, root)
        sync = dict(sync_row) if sync_row else None
    selected_complete = bool(
        sync and sync.get("outgoing_complete") and sync.get("incoming_complete")
        and _categories_include_erc20(sync.get("categories"))
    )

    return {
        "available": True,
        "records_examined": len(deduped),
        "assets": assets[:50],
        "edges": edges[:250],
        "coverage": {
            "record_limit": limit,
            "truncated": truncated,
            "selected_category_history_complete": selected_complete,
            "provider": sync.get("provider") if sync else None,
            "oldest_block": sync.get("oldest_block") if sync else None,
            "newest_block": sync.get("newest_block") if sync else None,
            "last_synced_at": sync.get("updated_at") if sync else None,
            "last_error": sync.get("last_error") if sync else None,
        },
        "scope": (
            "One-hop ERC-20 transfers from ChainScope's provider-indexed wallet evidence cache. "
            "Amounts are provider-normalized token quantities; no cross-asset value equivalence or token taint is inferred."
        ),
        "warning": (
            "Token movement is reported separately from native ETH paths. A transfer does not establish common ownership, "
            "intent, laundering, or conserved value through later swaps, bridges, or contract calls."
        ),
    }


@router.get("/{address}/graph")
async def wallet_graph(
    address: str,
    limit: int = Query(150, ge=1, le=400),
    depth: int = Query(2, ge=1, le=3),
    per_hop_limit: int = Query(120, ge=10, le=200),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    root = address.lower()
    visited, raw_edges, truncated, hop_stats = await _build_graph(repo, root, limit, depth, per_hop_limit)
    node_in = Counter(edge["target"] for edge in raw_edges)
    node_out = Counter(edge["source"] for edge in raw_edges)
    nodes = []
    for node in sorted(visited):
        connected_scores = [int(edge.get("risk_score") or 0) for edge in raw_edges if edge["source"] == node or edge["target"] == node]
        nodes.append({
            "id": node, "type": "address", "is_root": node == root,
            "incoming_edges": node_in[node], "outgoing_edges": node_out[node],
            "max_observed_risk_score": max(connected_scores) if connected_scores else 0,
        })
    return {
        "root": root, "chain_id": 1, "requested_depth": depth,
        "observed_depth": max((edge["hop"] for edge in raw_edges), default=0),
        "nodes": nodes, "edges": raw_edges, "paths": _directed_paths(root, raw_edges, depth),
        "motifs": _motifs(raw_edges),
        "coverage": {"edge_limit": limit, "per_hop_limit": per_hop_limit, "hop_stats": hop_stats, "truncated": truncated, "historical_completeness": False, "coverage_url": "/api/coverage"},
        "scope": "Observed native-ETH transfers retained by ChainScope; bounded multi-hop expansion, not full wallet history.",
        "provenance_warning": "A path or transfer is not proof of beneficial ownership, taint, intent, or ultimate destination.",
    }


@router.get("/{address}/fund-flow")
async def fund_flow_investigation(
    address: str,
    depth: int = Query(3, ge=1, le=3),
    limit: int = Query(300, ge=20, le=400),
    per_hop_limit: int = Query(160, ge=10, le=200),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Return native multi-hop flow plus separately scoped cached ERC-20 evidence."""
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    root = address.lower()
    visited, edges, truncated, hop_stats = await _build_graph(repo, root, limit, depth, per_hop_limit)
    paths = _directed_paths(root, edges, depth, max_paths=100)
    incoming = [edge for edge in edges if edge["target"] == root]
    outgoing = [edge for edge in edges if edge["source"] == root]
    incoming_wei = sum(int(edge["value_wei"]) for edge in incoming)
    outgoing_wei = sum(int(edge["value_wei"]) for edge in outgoing)
    by_counterparty = defaultdict(lambda: {"incoming_wei": 0, "outgoing_wei": 0, "tx_count": 0})
    for edge in incoming:
        row = by_counterparty[edge["source"]]
        row["incoming_wei"] += int(edge["value_wei"])
        row["tx_count"] += 1
    for edge in outgoing:
        row = by_counterparty[edge["target"]]
        row["outgoing_wei"] += int(edge["value_wei"])
        row["tx_count"] += 1
    counterparties = sorted(
        ({"address": addr, **stats, "total_wei": stats["incoming_wei"] + stats["outgoing_wei"]} for addr, stats in by_counterparty.items()),
        key=lambda item: item["total_wei"], reverse=True,
    )[:25]

    attributions = []
    try:
        rows = await repo.db.fetch("""
            SELECT address,source,entity_id,entity_name,entity_type,confidence,source_url,verified_at
            FROM entity_attributions
            WHERE chain_id=1 AND address=ANY($1::text[])
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY confidence DESC,verified_at DESC
        """, sorted(visited))
        attributions = [dict(row) for row in rows]
    except Exception:
        attributions = []
    labels_by_address = defaultdict(list)
    for item in attributions:
        labels_by_address[item["address"]].append(item)

    exposures = []
    for path in paths:
        destination = path["addresses"][-1]
        labels = labels_by_address.get(destination, [])
        if labels:
            exposures.append({
                "destination": destination,
                "hop_count": path["hop_count"],
                "path_min_value_wei": path["path_min_value_wei"],
                "tx_hashes": path["tx_hashes"],
                "entity_labels": labels,
                "evidence_urls": [f"https://etherscan.io/tx/{tx_hash}" for tx_hash in path["tx_hashes"]],
            })

    try:
        token_flow = await _token_flow_from_cache(repo, root)
    except Exception:
        token_flow = {
            "available": False,
            "records_examined": 0,
            "assets": [],
            "edges": [],
            "coverage": {"selected_category_history_complete": False, "reason": "token_cache_query_unavailable"},
            "scope": "ERC-20 evidence could not be loaded for this request.",
        }

    return {
        "root": root,
        "chain_id": 1,
        "flow_summary": {
            "observed_incoming_wei": str(incoming_wei),
            "observed_outgoing_wei": str(outgoing_wei),
            "observed_net_wei": str(incoming_wei - outgoing_wei),
            "incoming_tx_count": len(incoming),
            "outgoing_tx_count": len(outgoing),
            "unique_observed_addresses": len(visited),
        },
        "top_counterparties": counterparties,
        "directed_paths": paths,
        "entity_exposures": exposures,
        "token_flow": token_flow,
        "transaction_semantics": summarize_transfer_semantics(edges, token_flow.get("edges", [])),
        "motifs": _motifs(edges),
        "coverage": {"truncated": truncated, "hop_stats": hop_stats, "historical_completeness": False, "edge_limit": limit},
        "methodology": {
            "native_path_value": "minimum observed ETH transfer value across path edges; not fungible taint attribution",
            "token_flow": "one-hop provider-indexed cached ERC-20 evidence, aggregated per token contract without cross-asset conversion",
            "entity_matching": "source-attributed exact-address labels only; no inferred beneficial ownership",
            "scope": "bounded retained native ETH graph plus separately scoped cached ERC-20 evidence",
            "transaction_semantics": "co-occurring evidence only; no swap/bridge confirmation without decoded receipts, logs and execution traces",
        },
        "warning": (
            "Exposure means an observed bounded path reaches a source-labeled address. It is not proof that the root controls "
            "that entity, that funds are tainted, or that value is conserved across intermediate activity. ERC-20 transfers "
            "are not automatically chained through swaps, bridges, or later contract execution."
        ),
    }
