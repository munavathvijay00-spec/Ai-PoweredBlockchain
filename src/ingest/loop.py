"""
Ingest loop — runs forever, ingesting new canonical blocks every N seconds.

Normal shallow Ethereum reorgs are recovered only after a common ancestor is
cryptographically/evidentially verified. Deep or unverifiable forks still halt
fail-closed for manual review.

The live transaction table is intentionally tiny on the free-tier profile.
Blocks already older than the live window advance canonical lineage/checkpoint
without writing transaction rows that would immediately expire. Canonical
lineage itself is also pruned to a bounded recovery horizon.
"""
import asyncio
import signal
import sys
import time
from datetime import datetime
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.connection import get_db, close_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.risk.scorer import get_scorer
from src.agents.explainer import get_explainer
from src.ingest.worker import process_one_block
from src.ingest.cursor import ensure_cursor_schema, load_cursor_checkpoint, save_cursor_checkpoint, backfill_cursor_hash
from src.ingest.address_retention import prune_addresses
from src.ingest.storage_health import log_storage_health
from src.ingest.health_monitor import log_ingestion_health
from src.ingest.reorg import ensure_lineage_schema, record_lineage, recover_shallow_reorg
from src.storage_budget import LIVE_RETENTION_MINUTES, prune_lineage


_shutdown_requested = False
MAX_AUTO_REORG_DEPTH = 12


def _block_hash(value):
    if hasattr(value, 'hex'):
        result = value.hex()
    else:
        result = str(value)
    return (result if result.startswith('0x') else '0x' + result).lower()


def _handle_shutdown(signum, frame):
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


def catchup_batch_size(pending: int) -> int:
    """Bound how many sequential canonical successors are attempted per head check."""
    if pending > 100:
        return 12
    if pending > 20:
        return 6
    return 3


def catchup_sleep_seconds(pending_after_iteration: int, normal_interval: int) -> int:
    """Use short polling while behind, normal cadence near head."""
    if pending_after_iteration > 100:
        return min(normal_interval, 2)
    if pending_after_iteration > 20:
        return min(normal_interval, 5)
    return normal_interval


def block_outside_live_retention(block: dict, *, retention_minutes: int = LIVE_RETENTION_MINUTES, now_ts: int | None = None) -> bool:
    """Return True only when a block is definitely older than the live window."""
    if retention_minutes < 1:
        raise ValueError("retention_minutes must be positive")
    raw = block.get("timestamp")
    if raw is None:
        return False
    try:
        timestamp = int(raw)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now_ts is None else int(now_ts)
    return timestamp < current - retention_minutes * 60


def is_chain_integrity_failure(error: Exception) -> bool:
    """Classify integrity errors that must not be retried without verification."""
    message = str(error)
    return (
        'REORG_DETECTED:' in message
        or 'TRANSACTION_PROVENANCE_CONFLICT:' in message
        or 'CHECKPOINT_CONFLICT:' in message
        or 'LINEAGE_CONFLICT:' in message
    )


async def ingest_loop(interval_seconds: int = 15):
    logger.info(
        "🚀 Starting ingest loop (interval={}s, live_retention={}m)",
        interval_seconds,
        LIVE_RETENTION_MINUTES,
    )

    client = BlockchainClient()
    connected = await client.connect()
    if not connected:
        logger.error("❌ Blockchain connection failed. Exiting.")
        return

    db = await get_db()
    await ensure_cursor_schema(db)
    await ensure_lineage_schema(db)
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()

    iteration = 0
    total_inserted = 0
    total_flagged = 0
    total_header_only = 0
    last_processed_block, last_block_hash = await load_cursor_checkpoint(db)
    logger.info(f'Ingestion checkpoint restored: {last_processed_block}')
    latest_block = last_processed_block or 0

    try:
        while not _shutdown_requested:
            iteration += 1
            now = datetime.now().strftime("%H:%M:%S")

            try:
                logger.info(f"[{now}] 🔄 Iteration {iteration} — fetching latest block...")
                latest_block = await client.get_latest_block_number()

                if last_processed_block is None:
                    last_processed_block = latest_block - 1
                    tip_parent = await client.get_block(last_processed_block)
                    last_block_hash = _block_hash(tip_parent['hash'])
                    async with db.transaction():
                        await record_lineage(db, tip_parent)
                        await save_cursor_checkpoint(db, last_processed_block, last_block_hash)
                elif latest_block < last_processed_block:
                    log_ingestion_health(latest_block, last_processed_block)
                    logger.warning('Chain head below saved checkpoint; waiting for recovery')
                    await asyncio.sleep(interval_seconds)
                    continue

                if last_processed_block is not None and last_block_hash is None:
                    legacy_block = await client.get_block(last_processed_block)
                    last_block_hash = await backfill_cursor_hash(
                        db, last_processed_block, _block_hash(legacy_block['hash'])
                    )
                    logger.warning(
                        f'Legacy checkpoint anchored at block {last_processed_block}; earlier data is not reorg-verified'
                    )

                if last_block_hash is not None:
                    canonical = await client.get_block(last_processed_block)
                    canonical_hash = _block_hash(canonical['hash'])
                    if canonical_hash != last_block_hash.lower():
                        logger.warning(
                            'Checkpoint mismatch: height={} saved_hash={} rpc_hash={} head={} action=verify_bounded_rewind',
                            last_processed_block, last_block_hash, canonical_hash, latest_block,
                        )
                        recovery = await recover_shallow_reorg(
                            db,
                            client,
                            checkpoint_block=last_processed_block,
                            checkpoint_hash=last_block_hash,
                            max_depth=MAX_AUTO_REORG_DEPTH,
                        )
                        last_processed_block = recovery.ancestor_block
                        last_block_hash = recovery.ancestor_hash
                        logger.warning(
                            'Reorg recovered; replay will resume from block {} (depth={})',
                            last_processed_block + 1,
                            recovery.depth,
                        )

                pending = latest_block - last_processed_block
                batch_limit = catchup_batch_size(pending)
                if iteration == 1 or iteration % 4 == 0:
                    log_ingestion_health(latest_block, last_processed_block)
                if pending > batch_limit:
                    logger.info(
                        "Block catch-up: {} pending; processing up to {} sequentially",
                        pending,
                        batch_limit,
                    )

                recovered_mid_iteration = False
                for block_number in next_blocks(last_processed_block, latest_block, batch_limit):
                    header = await client.get_block(block_number, full_transactions=False)
                    if last_block_hash is not None and _block_hash(header['parentHash']) != last_block_hash.lower():
                        logger.warning(
                            'Successor parent mismatch at block {}; verifying bounded rewind before replay',
                            block_number,
                        )
                        recovery = await recover_shallow_reorg(
                            db,
                            client,
                            checkpoint_block=last_processed_block,
                            checkpoint_hash=last_block_hash,
                            max_depth=MAX_AUTO_REORG_DEPTH,
                        )
                        last_processed_block = recovery.ancestor_block
                        last_block_hash = recovery.ancestor_hash
                        recovered_mid_iteration = True
                        break

                    candidate_hash = _block_hash(header['hash'])
                    if block_outside_live_retention(header):
                        async with db.transaction():
                            await record_lineage(db, header)
                            await save_cursor_checkpoint(db, block_number, candidate_hash)
                        last_processed_block = block_number
                        last_block_hash = candidate_hash
                        total_header_only += 1
                        logger.info(
                            "⏩ Canonical block #{:,} advanced header-only; outside {}m live retention",
                            block_number,
                            LIVE_RETENTION_MINUTES,
                        )
                        continue

                    candidate = await client.get_block(block_number, full_transactions=True)
                    if _block_hash(candidate['hash']) != candidate_hash:
                        logger.warning(
                            'Block {} changed between header and full snapshot; deferring to reorg verification',
                            block_number,
                        )
                        recovered_mid_iteration = True
                        break

                    async with db.transaction():
                        summary = await process_one_block(
                            client, normalizer, transactions, addresses, scorer, explainer,
                            block_number=block_number,
                            prefetched_block=candidate,
                            allow_external_ai=False,
                        )
                        await record_lineage(db, candidate)
                        await save_cursor_checkpoint(db, block_number, candidate_hash)
                    last_processed_block = block_number
                    last_block_hash = candidate_hash
                    total_inserted += summary['inserted']
                    total_flagged += summary['flagged']
                    logger.success(
                        f"✅ Block #{summary['block_number']:,} | "
                        f"{summary['total_transactions']} txs | "
                        f"{summary['flagged']} flagged | "
                        f"{summary['explained']} explained | "
                        f"{summary['elapsed_seconds']}s"
                    )

                if recovered_mid_iteration:
                    logger.info('Canonical head changed mid-iteration; replay deferred to next iteration')
                elif pending == 0:
                    logger.debug("No new blocks at chain head")

                logger.info(
                    "📊 Session totals — Inserted: {:,} | Flagged: {} | Header-only catch-up: {}",
                    total_inserted,
                    total_flagged,
                    total_header_only,
                )

                if iteration == 1 or iteration % 60 == 0:
                    try:
                        await log_storage_health(db)
                    except Exception as storage_err:
                        logger.warning(f"Storage diagnostics unavailable: {storage_err}")

                # Free-tier profile: trim expired live rows aggressively so WAL/table
                # growth cannot run away between cleanup cycles.
                if iteration % 2 == 0:
                    try:
                        deleted = await db.execute(
                            """
                            DELETE FROM transactions
                            WHERE timestamp < NOW() - ($1 * INTERVAL '1 minute')
                            """,
                            LIVE_RETENTION_MINUTES,
                        )
                        logger.info(
                            "🗑️ Live retention cleanup ({}m): {}",
                            LIVE_RETENTION_MINUTES,
                            deleted,
                        )
                    except Exception as cleanup_err:
                        logger.warning(f"Transaction cleanup error (non-fatal): {cleanup_err}")

                    try:
                        await prune_addresses(
                            db,
                            enabled=True,
                            batch_size=500,
                            minutes=LIVE_RETENTION_MINUTES,
                        )
                    except Exception as cleanup_err:
                        logger.warning(f"Address cleanup error (non-fatal): {cleanup_err}")

                if iteration % 10 == 0:
                    try:
                        lineage_deleted = await prune_lineage(db, last_processed_block)
                        if lineage_deleted:
                            logger.info("🧹 Canonical lineage pruned: {} old rows", lineage_deleted)
                    except Exception as cleanup_err:
                        logger.warning(f"Lineage cleanup error (non-fatal): {cleanup_err}")

            except Exception as e:
                logger.exception(f"❌ Error in iteration {iteration}: {e}")
                if is_chain_integrity_failure(e):
                    logger.critical(
                        'Ingestion halted: integrity conflict exceeded automatic verification/recovery policy'
                    )
                    raise

            if not _shutdown_requested:
                remaining = max(0, latest_block - (last_processed_block or latest_block))
                sleep_seconds = catchup_sleep_seconds(remaining, interval_seconds)
                logger.debug(
                    "😴 Sleeping {}s (remaining_lag={} blocks)...",
                    sleep_seconds,
                    remaining,
                )
                await asyncio.sleep(sleep_seconds)

    finally:
        logger.info("🔌 Closing connections...")
        await client.close()
        await close_db()
        logger.success(f"✅ Ingest loop stopped after {iteration} iterations")


def main():
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
