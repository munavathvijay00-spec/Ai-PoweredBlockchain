import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg

from src.utils.config import get_settings


async def main():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        schema = Path(__file__).with_name('init.sql').read_text(encoding='utf-8')
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
