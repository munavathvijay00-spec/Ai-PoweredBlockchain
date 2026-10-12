"""Small durable checkpoint for the single Ethereum ingestion worker."""
from loguru import logger

CURSOR_KEY = "ethereum_mainnet"


async def ensure_cursor_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ingest_cursor (
            stream TEXT PRIMARY KEY,
            last_block BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def load_cursor(db):
    value = await db.fetchval(
        "SELECT last_block FROM ingest_cursor WHERE stream = $1", CURSOR_KEY
    )
    return int(value) if value is not None else None


async def save_cursor(db, block_number: int):
    """Checkpoint only completed blocks; never move the cursor backwards."""
    await db.execute("""
        INSERT INTO ingest_cursor (stream, last_block)
        VALUES ($1, $2)
        ON CONFLICT (stream) DO UPDATE
        SET last_block = GREATEST(ingest_cursor.last_block, EXCLUDED.last_block),
            updated_at = NOW()
    """, CURSOR_KEY, block_number)
