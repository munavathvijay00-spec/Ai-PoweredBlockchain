"""
Ingest loop — runs forever, ingesting new blocks every N seconds.

Usage:
    python -m src.ingest.loop
    python -m src.ingest.loop --interval 30   # custom interval

Press Ctrl+C to stop gracefully.
"""
import asyncio
import signal
import sys
from datetime import datetime
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.connection import get_db, close_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.risk.scorer import get_scorer
from src.agents.explainer import get_explainer
from src.ingest.worker import process_one_block


_shutdown_requested = False


def _handle_shutdown(signum, frame):
    """Handle Ctrl+C to allow graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("🛑 Shutdown requested. Finishing current iteration...")


async def ingest_loop(interval_seconds: int = 15):
    """Infinite loop: fetch latest block → process → sleep → repeat."""
    logger.info(f"🚀 Starting ingest loop (interval: {interval_seconds}s)")

    client = BlockchainClient()
    connected = await client.connect()
    if not connected:
        logger.error("❌ Blockchain connection failed. Exiting.")
        return

    db = await get_db()
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()

    iteration = 0
    total_inserted = 0
    total_flagged = 0

    try:
        while not _shutdown_requested:
            iteration += 1
            now = datetime.now().strftime("%H:%M:%S")

            try:
                logger.info(f"[{now}] 🔄 Iteration {iteration} — fetching latest block...")

                summary = await process_one_block(
                    client, normalizer, transactions, addresses, scorer, explainer
                )

                total_inserted += summary['inserted']
                total_flagged += summary['flagged']

                logger.success(
                    f"✅ Block #{summary['block_number']:,} | "
                    f"{summary['total_transactions']} txs | "
                    f"{summary['flagged']} flagged | "
                    f"{summary['explained']} explained | "
                    f"{summary['elapsed_seconds']}s"
                )
                logger.info(
                    f"📊 Session totals — Inserted: {total_inserted:,} | "
                    f"Flagged: {total_flagged}"
                )

            except Exception as e:
                logger.exception(f"❌ Error in iteration {iteration}: {e}")

            if not _shutdown_requested:
                logger.debug(f"😴 Sleeping {interval_seconds}s...")
                await asyncio.sleep(interval_seconds)

    finally:
        logger.info("🔌 Closing connections...")
        await client.close()
        await close_db()
        logger.success(f"✅ Ingest loop stopped after {iteration} iterations")


def main():
    """Entry point — parses args, sets up signal handlers, runs loop."""
    interval = 15
    if "--interval" in sys.argv:
        try:
            idx = sys.argv.index("--interval")
            interval = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Usage: python -m src.ingest.loop [--interval SECONDS]")
            sys.exit(1)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    try:
        asyncio.run(ingest_loop(interval_seconds=interval))
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")


if __name__ == "__main__":
    main()
