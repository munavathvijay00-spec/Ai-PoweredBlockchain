"""Apply the additive intelligence-v2 schema.

Usage:
    python scripts/migrate_intelligence_v2.py
    python -m scripts.migrate_intelligence_v2

No destructive statements are present in scripts/intelligence_v2.sql.
"""
import asyncio
import sys
from pathlib import Path

# Railway pre-deploy commands may invoke this file directly. In that mode Python
# places /app/scripts, not /app, on sys.path. Add the repository root explicitly
# before importing application modules so both invocation styles are reliable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg
from src.utils.config import get_settings

SQL = Path(__file__).with_name("intelligence_v2.sql")


async def main():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        sql = SQL.read_text(encoding="utf-8")
        async with conn.transaction():
            await conn.execute(sql)
        tables = await conn.fetch(
            """SELECT tablename FROM pg_catalog.pg_tables
               WHERE schemaname = current_schema()
                 AND tablename = ANY($1::text[])
               ORDER BY tablename""",
            [
                "wallet_transfer_evidence",
                "wallet_history_sync",
                "entity_attributions",
                "detection_labels",
                "detection_evaluations",
                "ingest_block_lineage",
            ],
        )
        expected = {
            "wallet_transfer_evidence",
            "wallet_history_sync",
            "entity_attributions",
            "detection_labels",
            "detection_evaluations",
            "ingest_block_lineage",
        }
        actual = {row["tablename"] for row in tables}
        missing = expected - actual
        if missing:
            raise RuntimeError(f"INTELLIGENCE_V2_INCOMPLETE: missing tables: {sorted(missing)}")
        print("INTELLIGENCE_V2_READY:", ", ".join(sorted(actual)))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
