"""Apply the additive intelligence-v2 schema.

Usage: python scripts/migrate_intelligence_v2.py
No destructive statements are present in scripts/intelligence_v2.sql.
"""
import asyncio
from pathlib import Path
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
            ],
        )
        print("INTELLIGENCE_V2_READY:", ", ".join(row["tablename"] for row in tables))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
