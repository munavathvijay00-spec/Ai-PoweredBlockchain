import asyncio
from pathlib import Path

import asyncpg

from src.utils.config import get_settings


async def main():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        schema = Path('/app/scripts/init.sql').read_text(encoding='utf-8')
        async with conn.transaction():
            await conn.execute(schema)
        required = {
            'addresses',
            'transactions',
            'alerts',
            'blacklist',
            'verified_address_intelligence',
        }
        rows = await conn.fetch(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = current_schema()"
        )
        present = {row['tablename'] for row in rows}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(f"Recovery schema initialization incomplete: {missing}")
        print('RECOVERY_SCHEMA_READY')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
