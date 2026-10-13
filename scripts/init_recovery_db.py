import asyncio
from pathlib import Path

import asyncpg

from src.utils.config import get_settings


async def main():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_catalog.pg_tables WHERE schemaname = current_schema() AND tablename IN ('addresses','transactions','alerts','blacklist','verified_address_intelligence','ingest_cursor')"
        )
        if existing:
            raise RuntimeError("Recovery database is not empty; initialization stopped")
        schema = Path('/app/scripts/init.sql').read_text(encoding='utf-8')
        async with conn.transaction():
            await conn.execute(schema)
        print('RECOVERY_SCHEMA_READY')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
