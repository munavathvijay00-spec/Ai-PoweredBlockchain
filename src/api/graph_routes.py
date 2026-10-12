"""Bounded graph of observed native ETH transfers, not inferred provenance."""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api/wallets", tags=["wallet intelligence"])
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def build_observed_graph(address: str, rows: list, truncated: bool) -> dict:
    """Keep exact raw wei and source hashes; no ownership or taint inference."""
    nodes = {address}
    edges = []
    for row in rows:
        source, target = row["from_address"].lower(), row["to_address"].lower()
        nodes.update((source, target))
        edges.append({
            "source": source, "target": target, "tx_hash": row["hash"],
            "block_number": row["block_number"],
            "value_wei": str(row["value_wei"]),
            "asset": "ETH", "chain_id": 1,
            "evidence_url": "https://etherscan.io/tx/" + row["hash"],
            "relationship": "observed_native_transaction",
        })
    return {
        "root": address, "chain_id": 1, "depth": 1,
        "nodes": [{"id": node, "type": "address"} for node in sorted(nodes)],
        "edges": edges, "truncated": truncated,
        "coverage_url": "/api/coverage", "historical_completeness": False,
        "scope": "Only recent native transactions retained by this platform; not full wallet history.",
        "provenance_warning": "A transfer is not proof of beneficial ownership, ultimate destination, or identifiable fund provenance.",
    }


@router.get("/{address}/graph")
async def wallet_graph(
    address: str,
    limit: int = Query(100, ge=1, le=200),
    depth: int = Query(1, ge=1, le=1),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not ADDRESS.fullmatch(address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum address")
    address = address.lower()
    rows = await repo.db.fetch("""
        SELECT t.hash, t.block_number, t.value::text AS value_wei,
               a_from.address AS from_address, a_to.address AS to_address
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE a_from.address = $1 OR a_to.address = $1
        ORDER BY t.block_number DESC, t.id DESC
        LIMIT $2
    """, address, limit + 1)
    return build_observed_graph(address, rows[:limit], len(rows) > limit)
