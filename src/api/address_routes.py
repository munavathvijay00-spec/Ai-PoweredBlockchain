from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_address_repo
from src.database.repositories import AddressRepository

router = APIRouter(prefix="/api", tags=["addresses"])

SORT_SQL = {
    "activity_desc": "tx_count DESC, a.last_seen DESC",
    "recent": "a.last_seen DESC",
    "oldest": "a.first_seen ASC",
    "risk_desc": "a.risk_score DESC NULLS LAST, tx_count DESC",
}


@router.get("/address-browser")
async def address_browser(
    limit: int = Query(50, ge=10, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=100),
    sort: Literal["activity_desc", "recent", "oldest", "risk_desc"] = "activity_desc",
    repo: AddressRepository = Depends(get_address_repo),
):
    where_sql = "TRUE"
    args = []
    if search:
        args.append(f"%{search.strip().lower()}%")
        where_sql = "lower(a.address) LIKE $1 OR lower(COALESCE(a.label, '')) LIKE $1"
    limit_param = len(args) + 1
    offset_param = len(args) + 2
    rows = await repo.db.fetch(f"""
        SELECT a.address, a.first_seen, a.last_seen, a.label, a.is_blacklisted,
               COALESCE(a.risk_score, 0) AS risk_score,
               COALESCE(outgoing.cnt, 0) + COALESCE(incoming.cnt, 0) AS tx_count,
               COALESCE(outgoing.cnt, 0) AS outgoing_count,
               COALESCE(incoming.cnt, 0) AS incoming_count
        FROM addresses a
        LEFT JOIN (
            SELECT from_address_id AS address_id, COUNT(*) AS cnt
            FROM transactions GROUP BY from_address_id
        ) outgoing ON outgoing.address_id=a.id
        LEFT JOIN (
            SELECT to_address_id AS address_id, COUNT(*) AS cnt
            FROM transactions GROUP BY to_address_id
        ) incoming ON incoming.address_id=a.id
        WHERE {where_sql}
        ORDER BY {SORT_SQL[sort]}
        LIMIT ${limit_param} OFFSET ${offset_param}
    """, *args, limit, offset)
    total = await repo.db.fetchval(f"SELECT COUNT(*) FROM addresses a WHERE {where_sql}", *args)
    return {
        "addresses": [dict(row) for row in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "has_previous": offset > 0,
        "has_next": offset + limit < int(total or 0),
    }
