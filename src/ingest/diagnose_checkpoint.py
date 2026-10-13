"""Read-only Ethereum ingestion checkpoint diagnostics.

Run: python -m src.ingest.diagnose_checkpoint
Does not mutate the database or ingestion cursor.
"""
import asyncio
from src.blockchain.client import BlockchainClient
from src.database.connection import get_db, close_db
from src.ingest.cursor import load_cursor_checkpoint


def block_hash(block):
    value = block["hash"]
    result = value.hex() if hasattr(value, "hex") else str(value)
    return result if result.startswith("0x") else "0x" + result


async def main():
    client = BlockchainClient()
    if not await client.connect():
        raise RuntimeError("Ethereum RPC connection or chain verification failed")
    try:
        db = await get_db()
        height, saved_hash = await load_cursor_checkpoint(db)
        if height is None:
            print("No checkpoint found; nothing to diagnose.")
            return
        tip = await client.get_latest_block_number()
        canonical = await client.get_block(height)
        observed = block_hash(canonical)
        print(f"checkpoint_height={height}")
        print(f"checkpoint_hash={saved_hash}")
        print(f"canonical_hash={observed}")
        print(f"chain_head={tip}")
        print(f"distance_from_head={tip - height}")
        print(f"hash_matches={bool(saved_hash and saved_hash.lower() == observed.lower())}")
        row = await db.fetchrow("""
            SELECT COUNT(*) AS retained_count,
                   MIN(block_number) AS min_height,
                   MAX(block_number) AS max_height,
                   COUNT(*) FILTER (WHERE block_number >= $1) AS at_or_after_checkpoint
            FROM transactions
        """, height)
        print("retained_transactions=" + str(dict(row)))
        print("action=read_only_no_checkpoint_changes")
    finally:
        await client.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
