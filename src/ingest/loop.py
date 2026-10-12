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
from src.ingest.cursor import ensure_cursor_schema, load_cursor, save_cursor
from src.ingest.address_retention import prune_addresses
from src.ingest.storage_health import log_storage_health
from src.ingest.health_monitor import log_ingestion_health
from src.risk.ofac_intelligence import ensure_intelligence_schema, refresh_ofac
from src.risk.wallet_exposure import ensure_exposure_schema


_shutdown_requested = False


def _handle_shutdown(signum, frame):
    """Handle Ctrl+C to allow graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("🛑 Shutdown requested. Finishing current iteration...")


def next_blocks(last_processed: int | None, latest: int, limit: int = 3) -> list[int]:
    """Return contiguous, bounded block numbers; no duplicates at a stable tip."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if last_processed is None or latest < last_processed:
        last_processed = latest - 1
    return list(range(last_processed + 1, min(latest, last_processed + limit) + 1))


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
        await ensure_exposure_schema(db)
        await refresh_ofac(db)
    except Exception as intelligence_err:
        logger.warning(f'Intelligence initialization failed (ingestion continues): {intelligence_err}')
    # Checkpoint is essential for gap-free recovery; fail startup if unavailable.
    await ensure_cursor_schema(db)
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()

    next_ofac_refresh = datetime.now() + timedelta(hours=24)
    iteration = 0
    total_inserted = 0
    total_flagged = 0
    # A missing or inaccessible checkpoint must not silently skip past failures.
    last_processed_block = await load_cursor(db)
    logger.info(f'Ingestion checkpoint restored: {last_processed_block}')
    max_blocks_per_iteration = 3

    try:
        while not _shutdown_requested:
            iteration += 1
            now = datetime.now().strftime("%H:%M:%S")

            try:
                logger.info(f"[{now}] 🔄 Iteration {iteration} — fetching latest block...")

                latest_block = await client.get_latest_block_number()
                if last_processed_block is None:
                    # First deployment: begin at tip; subsequent restarts resume.
                    last_processed_block = latest_block - 1
                    await save_cursor(db, last_processed_block)
                elif latest_block < last_processed_block:
                    # Never silently roll a durable checkpoint backwards.
                    log_ingestion_health(latest_block, last_processed_block)
                    logger.warning('Chain head below saved checkpoint; waiting for recovery')
                    continue

                pending = latest_block - last_processed_block
                if iteration == 1 or iteration % 4 == 0:
                    log_ingestion_health(latest_block, last_processed_block)
                if pending > max_blocks_per_iteration:
                    logger.info(
                        f"Block catch-up: {pending} pending; "
                        f"processing up to {max_blocks_per_iteration} sequentially"
                    )
                for block_number in next_blocks(
                    last_processed_block, latest_block, max_blocks_per_iteration
                ):
                    summary = await process_one_block(
                        client, normalizer, transactions, addresses, scorer, explainer,
                        block_number=block_number,
                    )
                    # Save checkpoint before advancing memory; retry after DB failure.
                    await save_cursor(db, block_number)
                    last_processed_block = block_number
                    total_inserted += summary['inserted']
                    total_flagged += summary['flagged']
                    logger.success(
                        f"✅ Block #{summary['block_number']:,} | "
                        f"{summary['total_transactions']} txs | "
                        f"{summary['flagged']} flagged | "
                        f"{summary['explained']} explained | "
                        f"{summary['elapsed_seconds']}s"
                    )
                if pending == 0:
                    logger.debug("No new blocks at chain head")
                logger.info(
                    f"📊 Session totals — Inserted: {total_inserted:,} | "
                    f"Flagged: {total_flagged}"
                )

                if datetime.now() >= next_ofac_refresh:
                    next_ofac_refresh = datetime.now() + timedelta(hours=24)
                    try:
                        await refresh_ofac(db)
                    except Exception as intelligence_err:
                        logger.warning(f'Intelligence refresh unavailable: {intelligence_err}')

                # Periodic lightweight size diagnostics (~15 minutes at default cadence).
                if iteration == 1 or iteration % 60 == 0:
                    try:
                        await log_storage_health(db)
                    except Exception as storage_err:
                        logger.warning(f"Storage diagnostics unavailable: {storage_err}")

                # Retain recent transactions; run once every ten iterations.
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

