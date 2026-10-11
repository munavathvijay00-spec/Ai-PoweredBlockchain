"""
Delete transactions older than N days to keep the DB size manageable.
Run: python -m scripts.cleanup_old_data [days]
"""
import asyncio
import sys
from loguru import logger

from src.database.connection import Database


async def cleanup(days: int = 3):
    """Delete transactions older than `days` days."""
    db = Database()
    connected = await db.connect()
    if not connected:
        logger.error("❌ Failed to connect to database")
        return

    logger.info(f"🗑️ Deleting transactions older than {days} days...")

    result = await db.execute(f"""
        DELETE FROM transactions 
        WHERE timestamp < NOW() - INTERVAL '{days} days'
    """)
    logger.info(f"✅ Delete result: {result}")

    result = await db.execute("""
        DELETE FROM addresses a
        WHERE NOT EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.from_address_id = a.id OR t.to_address_id = a.id
        )
    """)
    logger.info(f"✅ Orphaned addresses: {result}")

    logger.info("🔧 Running VACUUM...")
    await db.execute("VACUUM transactions")
    await db.execute("VACUUM addresses")
    logger.success("🎉 Cleanup complete")

    await db.close()


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(cleanup(days))