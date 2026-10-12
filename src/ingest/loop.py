"""
Ingest loop — runs forever, ingesting new blocks every N seconds.

Usage:
    python -m src.ingest.loop
    python -m src.ingest.loop --interval 30

Press Ctrl+C to stop gracefully.
"""
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.connection import get_db, close_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.risk.scorer import get_scorer
from src.agents.explainer import get_explainer
from src.ingest.worker import process_one_block
from src.ingest.address_retention import prune_addresses
from src.risk.ofac_intelligence import ensure_intelligence_schema, refresh_ofac


_shutdown_requested = False


def _handle_shutdown(signum, frame):
    """Handle Ctrl+C to allow graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("🛑 Shutdown requested. Finishing current iteration...")


async def ingest_loop(interval_seconds: int = 15):
    """Infinite loop: fetch latest block → process → sleep → repeat."""
    logger.info(f"🚀 Starting ingest loop (interval: {interval_seconds}s)")

    # Connect to blockchain
    client = BlockchainClient()
    connected = await client.connect()
    if not connected:
        logger.error("❌ Blockchain connection failed. Exiting.")
        return

    # Set up database + dependencies
    db = await get_db()
    try:
        await ensure_intelligence_schema(db)
        await refresh_ofac(db)
    except Exception as intelligence_err:
        logger.warning(f'Intelligence initialization failed (ingestion continues): {intelligence_err}')
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()

    next_ofac_refresh = datetime.now() + timedelta(hours=24)
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

                # Refresh verified source about every 24 hours at 15s cadence.\n                if iteration % 5760 == 0:\n                    await refresh_ofac(db)\n\n                # Retain recent transactions; run once every ten iterations.
                if iteration % 10 == 0:
                    try:
                        deleted = await db.execute("""
                            DELETE FROM transactions
                            WHERE timestamp < NOW() - INTERVAL '30 minutes'
                        """)
                        logger.info(f"🗑️ Retention cleanup: {deleted}")
                    except Exception as cleanup_err:
                        logger.warning(f"Transaction cleanup error (non-fatal): {cleanup_err}")

                # Bounded automatic address retention. Fail-closed guards live in
                # prune_addresses: FK inspection, linked records, intelligence fields,
                # and minimum 30-minute age. 500 rows every two iterations.
                if iteration % 2 == 0:
                    try:
                        await prune_addresses(db, enabled=True, batch_size=500, minutes=30)
                    except Exception as cleanup_err:
                        logger.warning(f"Address cleanup error (non-fatal): {cleanup_err}")

            except Exception as e:
                logger.exception(f"❌ Error in iteration {iteration}: {e}")

            # Sleep before next iteration
            if not _shutdown_requested:
                logger.debug(f"😴 Sleeping {interval_seconds}s...")
                await asyncio.sleep(interval_seconds)

    finally:
        logger.info("🔌 Closing connections...")
        await client.close()
        await close_db()
        logger.success(f"✅ Ingest loop stopped after {iteration} iterations")


def main():
    """Entry point."""
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

