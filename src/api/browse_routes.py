"""Transaction browsing endpoints with one consistent filtered population."""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from src.api.dependencies import get_transaction_repo
from src.api.routes import _format_tx, _load_entity_matches
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api", tags=["blockchain-browser"])

SORT_SQL = {
    "newest": "t.timestamp DESC, t.id DESC",
    "oldest": "t.timestamp ASC, t.id ASC",
    "risk_desc": "t.risk_score DESC, t.timestamp DESC, t.id DESC",
    "risk_asc": "t.risk_score ASC, t.timestamp DESC, t.id DESC",
    "value_desc": "t.value DESC, t.timestamp DESC, t.id DESC",
    "value_asc": "t.value ASC, t.timestamp DESC, t.id DESC",
}


def _where(search: str | None, min_risk: int | None, max_risk: int | None,
           min_value_eth: float | None, max_value_eth: float | None):
    clauses = []
    args = []

    def add(sql: str, value):
        args.append(value)
        clauses.append(sql.replace("?", f"${len(args)}"))

    if search:
        add("(lower(t.hash) LIKE ? OR lower(a_from.address) LIKE ? OR lower(a_to.address) LIKE ?)", f"%{search.strip().lower()}%")
        # The same search value is referenced three times; expand safely.
        value = args.pop()
        clauses.pop()
        args.extend([value, value, value])
        n = len(args)
        clauses.append(f"(lower(t.hash) LIKE ${n-2} OR lower(a_from.address) LIKE ${n-1} OR lower(a_to.address) LIKE ${n})")
    if min_risk is not None:
        add("t.risk_score >= ?", int(min_risk))
    if max_risk is not None:
        add("t.risk_score <= ?", int(max_risk))
    if min_value_eth is not None:
        add("t.value >= ?", Decimal(str(min_value_eth)) * Decimal(10**18))
    if max_value_eth is not None:
        add("t.value <= ?", Decimal(str(max_value_eth)) * Decimal(10**18))

    return (" AND ".join(clauses) if clauses else "TRUE"), args


async def _query_population(repo: TransactionRepository, *, search=None, min_risk=None, max_risk=None,
                            min_value_eth=None, max_value_eth=None, limit=50, offset=0,
                            sort="newest"):
    where_sql, args = _where(search, min_risk, max_risk, min_value_eth, max_value_eth)
    order_sql = SORT_SQL[sort]
    page_limit_param = len(args) + 1
    offset_param = len(args) + 2
    rows = await repo.db.fetch(f"""
        SELECT t.hash, a_from.address AS from_address, a_to.address AS to_address,
               t.value, t.block_number, t.timestamp, t.risk_score,
               t.risk_factors, t.ai_explanation
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ${page_limit_param} OFFSET ${offset_param}
    """, *args, limit, offset)

    aggregate = await repo.db.fetchrow(f"""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE t.risk_score < 20) AS minimal,
               COUNT(*) FILTER (WHERE t.risk_score >= 20 AND t.risk_score < 40) AS review,
               COUNT(*) FILTER (WHERE t.risk_score >= 40 AND t.risk_score < 80) AS high_review,
               COUNT(*) FILTER (WHERE t.risk_score >= 80) AS critical,
               MIN(t.timestamp) AS oldest_timestamp,
               MAX(t.timestamp) AS newest_timestamp,
               MAX(t.block_number) AS newest_block
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE {where_sql}
    """, *args)
    return rows, dict(aggregate or {})


@router.get("/transaction-browser")
async def transaction_browser(
    limit: int = Query(50, ge=10, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=100),
    min_risk: int | None = Query(None, ge=0, le=100),
    max_risk: int | None = Query(None, ge=0, le=100),
    min_value_eth: float | None = Query(None, ge=0),
    max_value_eth: float | None = Query(None, ge=0),
    sort: Literal["newest", "oldest", "risk_desc", "risk_asc", "value_desc", "value_asc"] = "newest",
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Return one filtered page plus distribution counts over that exact same population."""
    rows, aggregate = await _query_population(
        repo, search=search, min_risk=min_risk, max_risk=max_risk,
        min_value_eth=min_value_eth, max_value_eth=max_value_eth,
        limit=limit, offset=offset, sort=sort,
    )
    matches = await _load_entity_matches(repo, rows)
    total = int(aggregate.get("total") or 0)
    return {
        "transactions": [_format_tx(row, matches) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_previous": offset > 0,
        "has_next": offset + limit < total,
        "distribution": {
            "population": total,
            "minimal": int(aggregate.get("minimal") or 0),
            "review": int(aggregate.get("review") or 0),
            "high_review": int(aggregate.get("high_review") or 0),
            "critical": int(aggregate.get("critical") or 0),
        },
        "population_scope": "All retained transactions matching the current filters; chart counts are not sampled from the visible page.",
        "oldest_timestamp": aggregate.get("oldest_timestamp"),
        "newest_timestamp": aggregate.get("newest_timestamp"),
        "newest_block": aggregate.get("newest_block"),
    }


@router.get("/transaction-export")
async def transaction_export(
    format: Literal["csv", "json"] = "csv",
    search: str | None = Query(None, max_length=100),
    min_risk: int | None = Query(None, ge=0, le=100),
    max_risk: int | None = Query(None, ge=0, le=100),
    min_value_eth: float | None = Query(None, ge=0),
    max_value_eth: float | None = Query(None, ge=0),
    sort: Literal["newest", "oldest", "risk_desc", "risk_asc", "value_desc", "value_asc"] = "newest",
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Export at most 5,000 rows matching the same browser filters."""
    rows, aggregate = await _query_population(
        repo, search=search, min_risk=min_risk, max_risk=max_risk,
        min_value_eth=min_value_eth, max_value_eth=max_value_eth,
        limit=5000, offset=0, sort=sort,
    )
    data = [{
        "hash": row["hash"], "from_address": row["from_address"], "to_address": row["to_address"],
        "value_wei": str(row["value"]), "block_number": row["block_number"],
        "timestamp": row["timestamp"].isoformat() if row.get("timestamp") else None,
        "risk_score": row.get("risk_score", 0),
    } for row in rows]
    headers = {
        "X-ChainScope-Matching-Rows": str(int(aggregate.get("total") or 0)),
        "X-ChainScope-Exported-Rows": str(len(data)),
        "X-ChainScope-Export-Limit": "5000",
    }
    if format == "json":
        import json
        return Response(content=json.dumps({"rows": data, "matching_rows": int(aggregate.get("total") or 0), "export_limit": 5000}), media_type="application/json", headers=headers)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["hash", "from_address", "to_address", "value_wei", "block_number", "timestamp", "risk_score"])
    writer.writeheader()
    writer.writerows(data)
    headers["Content-Disposition"] = 'attachment; filename="chainscope-transactions.csv"'
    return Response(content=out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)
