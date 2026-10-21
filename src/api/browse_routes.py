"""Transaction browsing endpoints with a clustered analyst review queue."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from datetime import datetime, timezone
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

CLUSTER_SORT_SQL = {
    "newest": "stats.newest_timestamp DESC, ranked.id DESC",
    "oldest": "stats.oldest_timestamp ASC, ranked.id ASC",
    "risk_desc": "ranked.risk_score DESC, stats.cluster_count DESC, stats.newest_timestamp DESC, ranked.id DESC",
    "risk_asc": "ranked.risk_score ASC, stats.cluster_count DESC, stats.newest_timestamp DESC, ranked.id DESC",
    "value_desc": "ranked.value DESC, stats.newest_timestamp DESC, ranked.id DESC",
    "value_asc": "ranked.value ASC, stats.newest_timestamp DESC, ranked.id DESC",
}


def _where(search: str | None, min_risk: int | None, max_risk: int | None,
           min_value_eth: float | None, max_value_eth: float | None):
    clauses: list[str] = []
    args: list[object] = []

    def add(sql: str, value):
        args.append(value)
        clauses.append(sql.replace("?", f"${len(args)}"))

    if search and search.strip():
        # Treat wallet hashes and addresses as literal substrings. Unescaped
        # '%' and '_' would otherwise produce unexpectedly broad matches.
        term = search.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        value = f"%{term}%"
        args.extend([value, value, value])
        n = len(args)
        clauses.append(
            f"(lower(t.hash) LIKE ${n-2} ESCAPE E'\\\\' OR "
            f"lower(a_from.address) LIKE ${n-1} ESCAPE E'\\\\' OR "
            f"lower(a_to.address) LIKE ${n} ESCAPE E'\\\\')"
        )
    if min_risk is not None:
        add("t.risk_score >= ?", int(min_risk))
    if max_risk is not None:
        add("t.risk_score <= ?", int(max_risk))
    if min_value_eth is not None:
        add("t.value >= ?", Decimal(str(min_value_eth)) * Decimal(10**18))
    if max_value_eth is not None:
        add("t.value <= ?", Decimal(str(max_value_eth)) * Decimal(10**18))

    return (" AND ".join(clauses) if clauses else "TRUE"), args


async def _aggregate_population(repo: TransactionRepository, where_sql: str, args: list[object]):
    row = await repo.db.fetchrow(f"""
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT t.block_number) AS distinct_blocks,
               COUNT(*) FILTER (WHERE t.risk_score < 20) AS minimal,
               COUNT(*) FILTER (WHERE t.risk_score >= 20 AND t.risk_score < 40) AS review,
               COUNT(*) FILTER (WHERE t.risk_score >= 40 AND t.risk_score < 80) AS high_review,
               COUNT(*) FILTER (WHERE t.risk_score >= 80) AS critical,
               MIN(t.timestamp) AS oldest_timestamp,
               MAX(t.timestamp) AS newest_timestamp,
               MIN(t.block_number) AS oldest_block,
               MAX(t.block_number) AS newest_block
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE {where_sql}
    """, *args)
    return dict(row or {})


async def _query_population(repo: TransactionRepository, *, search=None, min_risk=None, max_risk=None,
                            min_value_eth=None, max_value_eth=None, limit=50, offset=0,
                            sort="newest"):
    where_sql, args = _where(search, min_risk, max_risk, min_value_eth, max_value_eth)
    order_sql = SORT_SQL[sort]
    rows = await repo.db.fetch(f"""
        SELECT t.hash, a_from.address AS from_address, a_to.address AS to_address,
               t.value, t.block_number, t.timestamp, t.risk_score,
               t.risk_factors, t.ai_explanation,
               COUNT(*) OVER (PARTITION BY t.from_address_id, t.to_address_id) AS same_pair_count
        FROM transactions t
        JOIN addresses a_from ON t.from_address_id = a_from.id
        JOIN addresses a_to ON t.to_address_id = a_to.id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}
    """, *args, limit, offset)
    aggregate = await _aggregate_population(repo, where_sql, args)
    return [dict(row) for row in rows], aggregate


async def _query_clusters(repo: TransactionRepository, *, search=None, min_risk=None, max_risk=None,
                          min_value_eth=None, max_value_eth=None, limit=50, offset=0,
                          sort="risk_desc"):
    """Collapse repeated sender→recipient activity into one reproducible review row."""
    where_sql, args = _where(search, min_risk, max_risk, min_value_eth, max_value_eth)
    order_sql = CLUSTER_SORT_SQL[sort]
    rows = await repo.db.fetch(f"""
        WITH filtered AS (
            SELECT t.id, t.hash, t.from_address_id, t.to_address_id,
                   a_from.address AS from_address, a_to.address AS to_address,
                   t.value, t.block_number, t.timestamp, t.risk_score,
                   t.risk_factors, t.ai_explanation
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE {where_sql}
        ),
        ranked AS (
            SELECT filtered.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY from_address_id, to_address_id
                       ORDER BY risk_score DESC, timestamp DESC, id DESC
                   ) AS cluster_rank
            FROM filtered
        ),
        stats AS (
            SELECT from_address_id, to_address_id,
                   COUNT(*) AS cluster_count,
                   MIN(timestamp) AS oldest_timestamp,
                   MAX(timestamp) AS newest_timestamp,
                   COUNT(DISTINCT block_number) AS cluster_blocks,
                   ARRAY_AGG(hash ORDER BY timestamp DESC, id DESC)
                       FILTER (WHERE cluster_rank <= 100) AS cluster_hashes
            FROM ranked
            GROUP BY from_address_id, to_address_id
        )
        SELECT ranked.id AS representative_id, ranked.hash, ranked.from_address, ranked.to_address,
               ranked.value, ranked.block_number, ranked.timestamp, ranked.risk_score,
               ranked.risk_factors, ranked.ai_explanation,
               stats.cluster_count, stats.oldest_timestamp, stats.newest_timestamp,
               stats.cluster_blocks, stats.cluster_hashes
        FROM ranked
        JOIN stats USING (from_address_id, to_address_id)
        WHERE ranked.cluster_rank = 1
        ORDER BY {order_sql}
        LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}
    """, *args, limit, offset)

    total = await repo.db.fetchval(f"""
        SELECT COUNT(*) FROM (
            SELECT t.from_address_id, t.to_address_id
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE {where_sql}
            GROUP BY t.from_address_id, t.to_address_id
        ) grouped
    """, *args)
    return [dict(row) for row in rows], int(total or 0)


def _decorate_row(row: dict, matches, clustered: bool):
    count = int(row.get("cluster_count") or row.get("same_pair_count") or 1)
    row["relationship_context"] = {
        "self_transfer": str(row.get("from_address") or "").lower() == str(row.get("to_address") or "").lower(),
        "same_pair_count": count,
    }
    formatted = _format_tx(row, matches)
    # _format_tx intentionally returns a validated Pydantic response model. Convert it
    # at this boundary before adding browse-only cluster metadata.
    item = formatted.model_dump(mode="json") if hasattr(formatted, "model_dump") else dict(formatted)
    if clustered:
        item["cluster"] = {
            "kind": "address_pair",
            "count": count,
            "hashes": list(row.get("cluster_hashes") or []),
            "hashes_truncated": count > len(row.get("cluster_hashes") or []),
            "oldest_timestamp": row.get("oldest_timestamp"),
            "newest_timestamp": row.get("newest_timestamp"),
            "distinct_blocks": int(row.get("cluster_blocks") or 0),
        }
    return item


@router.get("/transaction-browser")
async def transaction_browser(
    limit: int = Query(50, ge=10, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=100),
    min_risk: int | None = Query(None, ge=0, le=100),
    max_risk: int | None = Query(None, ge=0, le=100),
    min_value_eth: float | None = Query(None, ge=0),
    max_value_eth: float | None = Query(None, ge=0),
    sort: Literal["newest", "oldest", "risk_desc", "risk_asc", "value_desc", "value_asc"] = "risk_desc",
    clustered: bool = Query(True),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    where_sql, where_args = _where(search, min_risk, max_risk, min_value_eth, max_value_eth)
    async with repo.db.transaction(isolation="repeatable_read", readonly=True):
        aggregate = await _aggregate_population(repo, where_sql, where_args)
        transaction_total = int(aggregate.get("total") or 0)

        if clustered:
            rows, queue_total = await _query_clusters(
                repo, search=search, min_risk=min_risk, max_risk=max_risk,
                min_value_eth=min_value_eth, max_value_eth=max_value_eth,
                limit=limit, offset=offset, sort=sort,
            )
        else:
            rows, _ = await _query_population(
                repo, search=search, min_risk=min_risk, max_risk=max_risk,
                min_value_eth=min_value_eth, max_value_eth=max_value_eth,
                limit=limit, offset=offset, sort=sort,
            )
            queue_total = transaction_total

    matches = await _load_entity_matches(repo, rows)
    formatted = [_decorate_row(row, matches, clustered) for row in rows]
    page_blocks = {int(row["block_number"]) for row in rows if row.get("block_number") is not None}
    distinct_blocks = int(aggregate.get("distinct_blocks") or 0)

    return {
        "transactions": formatted,
        "total": queue_total,
        "matching_transactions": transaction_total,
        "clustered": clustered,
        "limit": limit,
        "offset": offset,
        "has_previous": offset > 0,
        "has_next": offset + limit < queue_total,
        "distribution": {
            "population": transaction_total,
            "minimal": int(aggregate.get("minimal") or 0),
            "review": int(aggregate.get("review") or 0),
            "high_review": int(aggregate.get("high_review") or 0),
            "critical": int(aggregate.get("critical") or 0),
        },
        "population_scope": (
            f"{queue_total:,} review clusters represent {transaction_total:,} retained transactions matching the current filters."
            if clustered
            else "All retained transactions matching the current filters; chart counts are not sampled from the visible page."
        ),
        "distinct_blocks": distinct_blocks,
        "page_distinct_blocks": len(page_blocks),
        "oldest_timestamp": aggregate.get("oldest_timestamp"),
        "newest_timestamp": aggregate.get("newest_timestamp"),
        "oldest_block": aggregate.get("oldest_block"),
        "newest_block": aggregate.get("newest_block"),
    }


def _evidence_digest(items: list[dict]) -> str:
    """Fingerprint exported record contents independent of JSON/CSV formatting.

    This is an integrity checksum, not proof of chain finality, completeness
    or permanent evidence retention. The verifier must retain the export.
    """
    fields = ("hash", "from_address", "to_address", "value_wei",
              "block_number", "timestamp", "risk_score", "risk_factors")
    normalized = [
        {field: item.get(field) for field in fields}
        for item in items
    ]
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                           default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@router.get("/transaction-export")
async def transaction_export(
    format: Literal["csv", "json", "bundle"] = "csv",
    search: str | None = Query(None, max_length=100),
    min_risk: int | None = Query(None, ge=0, le=100),
    max_risk: int | None = Query(None, ge=0, le=100),
    min_value_eth: float | None = Query(None, ge=0),
    max_value_eth: float | None = Query(None, ge=0),
    sort: Literal["newest", "oldest", "risk_desc", "risk_asc", "value_desc", "value_asc"] = "risk_desc",
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    async with repo.db.transaction(isolation="repeatable_read", readonly=True):
        rows, aggregate = await _query_population(
            repo, search=search, min_risk=min_risk, max_risk=max_risk,
            min_value_eth=min_value_eth, max_value_eth=max_value_eth,
            limit=5000, offset=0, sort=sort,
        )
    matches = await _load_entity_matches(repo, rows)
    items = [_decorate_row(row, matches, False) for row in rows]
    evidence_sha256 = _evidence_digest(items)
    if format == "bundle":
        # A self-contained export that can be preserved offline. The digest
        # covers the evidence rows, not this envelope or unverifiable claims.
        return Response(
            content=json.dumps({
                "schema_version": "chainscope-evidence-bundle-v1",
                "chain_id": 1,
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "collection": "retained native Ethereum transactions matching export filters",
                "source": "chainscope-retained-postgresql-snapshot",
                "filters": {
                    "search": search, "min_risk": min_risk, "max_risk": max_risk,
                    "min_value_eth": min_value_eth, "max_value_eth": max_value_eth,
                    "sort": sort,
                },
                "coverage": {
                    "matching_transactions": int(aggregate.get("total") or 0),
                    "exported_transactions": len(items),
                    "truncated": int(aggregate.get("total") or 0) > len(items),
                    "oldest_block": aggregate.get("oldest_block"),
                    "newest_block": aggregate.get("newest_block"),
                    "historical_completeness": False,
                    "limitations": [
                        "The hot-table retention window excludes older chain history.",
                        "Block canonicality and chain finality are not established by this export.",
                        "A digest proves byte-equivalent evidence fields, not authenticity.",
                        "No server-side archival or legal chain of custody is claimed.",
                    ],
                },
                "integrity": {
                    "algorithm": "sha256",
                    "digest": evidence_sha256,
                    "canonicalization": "fields in _evidence_digest; sorted keys; compact UTF-8 JSON; original row order",
                },
                "transactions": items,
            }, default=str, separators=(",", ":"), ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=chainscope-evidence-bundle.json",
                     "Cache-Control": "no-store"},
        )
    if format == "json":
        return {
            "transactions": items,
            "count": len(items),
            "matching_transactions": int(aggregate.get("total") or 0),
            "truncated": int(aggregate.get("total") or 0) > len(items),
            "evidence_sha256": evidence_sha256,
            "hash_algorithm": "sha256",
            "evidence_scope": "exported rows only; not a durable archive or complete chain history",
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["hash", "from_address", "to_address", "value_wei", "value_eth", "block_number", "timestamp", "risk_score", "explanation_status", "risk_factors_json"])
    for item in items:
        writer.writerow([
            item.get("hash"), item.get("from_address"), item.get("to_address"),
            item.get("value_wei"), item.get("value_eth"), item.get("block_number"),
            item.get("timestamp"), item.get("risk_score"), item.get("explanation_status"),
            json.dumps(item.get("risk_factors") or [], sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=chainscope-transactions.csv",
            "X-Export-Matching-Transactions": str(int(aggregate.get("total") or 0)),
            "X-Export-Returned-Transactions": str(len(items)),
            "X-Export-Truncated": "true" if int(aggregate.get("total") or 0) > len(items) else "false",
            "X-Evidence-SHA256": evidence_sha256,
        },
    )
