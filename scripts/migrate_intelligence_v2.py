"""Apply the base ChainScope schema and additive intelligence-v2 schema.

This migration is intentionally idempotent so a freshly wiped recovery database
can be rebuilt safely on the existing free Railway volume.

Usage:
    python scripts/migrate_intelligence_v2.py
    python -m scripts.migrate_intelligence_v2
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg
from src.utils.config import get_settings

BASE_SQL = Path(__file__).with_name("init.sql")
INTELLIGENCE_SQL = Path(__file__).with_name("intelligence_v2.sql")

BASE_TABLES = {
    "addresses",
    "transactions",
    "alerts",
    "blacklist",
    "verified_address_intelligence",
}

INTELLIGENCE_TABLES = {
    "wallet_transfer_evidence",
    "wallet_history_sync",
    "entity_attributions",
    "detection_labels",
    "detection_evaluations",
    "ingest_block_lineage",
}


async def _require_tables(conn, expected: set[str], label: str) -> set[str]:
    tables = await conn.fetch(
        """SELECT tablename FROM pg_catalog.pg_tables
           WHERE schemaname = current_schema()
             AND tablename = ANY($1::text[])
           ORDER BY tablename""",
        sorted(expected),
    )
    actual = {row["tablename"] for row in tables}
    missing = expected - actual
    if missing:
        raise RuntimeError(f"{label}_INCOMPLETE: missing tables: {sorted(missing)}")
    return actual


async def main():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        base_sql = BASE_SQL.read_text(encoding="utf-8")
        intelligence_sql = INTELLIGENCE_SQL.read_text(encoding="utf-8")

        async with conn.transaction():
            await conn.execute(base_sql)
        base_actual = await _require_tables(conn, BASE_TABLES, "BASE_SCHEMA")
        print("BASE_SCHEMA_READY:", ", ".join(sorted(base_actual)))

        async with conn.transaction():
            await conn.execute(intelligence_sql)
        intelligence_actual = await _require_tables(
            conn, INTELLIGENCE_TABLES, "INTELLIGENCE_V2"
        )
        print("INTELLIGENCE_V2_READY:", ", ".join(sorted(intelligence_actual)))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
