"""Small durable checkpoint for the single Ethereum ingestion worker."""
from loguru import logger

CURSOR_KEY = "ethereum_mainnet"


def validate_block_hash(block_hash: str) -> None:
    """Require an exact 32-byte hexadecimal Ethereum block hash."""
    if (
        not isinstance(block_hash, str)
        or len(block_hash) != 66
        or not block_hash.startswith("0x")
        or any(char not in "0123456789abcdefABCDEF" for char in block_hash[2:])
    ):
        raise ValueError("Expected a 32-byte hexadecimal block hash")


async def ensure_cursor_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ingest_cursor (
            stream TEXT PRIMARY KEY,
            last_block BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("ALTER TABLE ingest_cursor ADD COLUMN IF NOT EXISTS block_hash TEXT")


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


async def load_cursor_checkpoint(db):
    """Return last block and canonical hash, if recorded."""
    row = await db.fetchrow(
        "SELECT last_block, block_hash FROM ingest_cursor WHERE stream = $1",
        CURSOR_KEY,
    )
    return (int(row["last_block"]), row["block_hash"]) if row else (None, None)


async def save_cursor_checkpoint(db, block_number: int, block_hash: str):
    """Advance only; store the block hash with the corresponding height atomically."""
    validate_block_hash(block_hash)
    row = await db.fetchrow("""
        INSERT INTO ingest_cursor (stream, last_block, block_hash)
        VALUES ($1, $2, $3)
        ON CONFLICT (stream) DO UPDATE
        SET last_block = EXCLUDED.last_block,
            block_hash = EXCLUDED.block_hash,
            updated_at = NOW()
        WHERE ingest_cursor.last_block < EXCLUDED.last_block
        RETURNING last_block, block_hash
    """, CURSOR_KEY, block_number, block_hash)
    if (
        not row
        or int(row["last_block"]) != block_number
        or row["block_hash"] != block_hash
    ):
        raise RuntimeError(
            "CHECKPOINT_CONFLICT: checkpoint did not advance to requested canonical block"
        )


async def rewind_cursor_checkpoint(
    db,
    *,
    expected_block: int,
    expected_hash: str,
    ancestor_block: int,
    ancestor_hash: str,
):
    """Explicitly rewind after a verified canonical reorg.

    This is the only allowed backward cursor move. It uses compare-and-swap
    against the exact checkpoint being recovered so concurrent or stale workers
    fail closed rather than overwriting newer progress.
    """
    validate_block_hash(expected_hash)
    validate_block_hash(ancestor_hash)
    if ancestor_block >= expected_block:
        raise ValueError("ancestor must be below the checkpoint being rewound")
    row = await db.fetchrow("""
        UPDATE ingest_cursor
        SET last_block = $4, block_hash = $5, updated_at = NOW()
        WHERE stream = $1
          AND last_block = $2
          AND lower(block_hash) = lower($3)
        RETURNING last_block, block_hash
    """, CURSOR_KEY, expected_block, expected_hash, ancestor_block, ancestor_hash)
    if (
        not row
        or int(row["last_block"]) != ancestor_block
        or row["block_hash"].lower() != ancestor_hash.lower()
    ):
        raise RuntimeError("CHECKPOINT_CONFLICT: checkpoint changed during verified reorg rewind")
    logger.warning(
        "Verified reorg rewind: checkpoint {} -> {}",
        expected_block,
        ancestor_block,
    )
    return ancestor_block, row["block_hash"]


async def backfill_cursor_hash(db, block_number: int, block_hash: str) -> str:
    """Fill a legacy NULL hash only at the unchanged cursor height.

    Never overwrite an existing hash or alter the saved height. A concurrent
    cursor advance must cause this operation to fail closed.
    """
    validate_block_hash(block_hash)
    row = await db.fetchrow("""
        UPDATE ingest_cursor
        SET block_hash = $3, updated_at = NOW()
        WHERE stream = $1 AND last_block = $2 AND block_hash IS NULL
        RETURNING block_hash
    """, CURSOR_KEY, block_number, block_hash)
    if not row:
        raise RuntimeError("CHECKPOINT_CONFLICT: legacy cursor changed during hash backfill")
    return row["block_hash"]
