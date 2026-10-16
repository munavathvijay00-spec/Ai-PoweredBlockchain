"""Bounded multi-hop graph and fund-flow investigation primitives over retained transfers."""
from collections import Counter, defaultdict, deque
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/wallets", tags=["wallet intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


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
    """Return investigation-oriented flow metrics, paths and source-attributed entity exposure."""
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
        row = by_counterparty[edge["source"]]; row["incoming_wei"] += int(edge["value_wei"]); row["tx_count"] += 1
    for edge in outgoing:
        row = by_counterparty[edge["target"]]; row["outgoing_wei"] += int(edge["value_wei"]); row["tx_count"] += 1
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
        "motifs": _motifs(edges),
        "coverage": {"truncated": truncated, "hop_stats": hop_stats, "historical_completeness": False, "edge_limit": limit},
        "methodology": {
            "path_value": "minimum observed transfer value across path edges; not fungible taint attribution",
            "entity_matching": "source-attributed address labels only; no inferred beneficial ownership",
            "scope": "retained native ETH transaction graph only",
        },
        "warning": "Exposure means an observed bounded path reaches a source-labeled address. It is not proof that the root controls that entity, that funds are tainted, or that value is conserved across intermediate activity.",
    }
