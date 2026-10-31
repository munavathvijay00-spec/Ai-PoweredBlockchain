"""One-block, opt-in Ethereum demo refresh. Never a continuous ingestion worker."""
import asyncio
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.repositories import AddressRepository, TransactionRepository
from src.ingest.worker import process_one_block
from src.risk.scorer import get_scorer
from src.agents.explainer import get_explainer

async def refresh_demo_block(db):
    """Fetch one sufficiently confirmed mainnet block; atomic and fail-closed."""
    client = BlockchainClient()
    try:
        if not await client.connect():
            raise RuntimeError("Ethereum mainnet RPC verification failed")
        head = await client.get_latest_block_number()
        target = head - 8
        if target < 1:
            raise RuntimeError("No safe block available for demo refresh")
        block = await client.get_block(target, full_transactions=True)
        addresses = AddressRepository(db)
        transactions = TransactionRepository(db, addresses)
        async with db.transaction():
            result = await process_one_block(
                client, TransactionNormalizer(), transactions, addresses,
                get_scorer(), get_explainer(), block_number=target,
                prefetched_block=block, allow_external_ai=False,
            )
        logger.info(
            "Demo refresh succeeded block={} inserted={} flagged={}",
            result["block_number"], result["inserted"], result["flagged"],
        )
        return result
    finally:
        await client.close()

async def safe_startup_demo_refresh(db):
    """Never prevent API startup or retry indefinitely on an unavailable provider."""
    try:
        return await asyncio.wait_for(refresh_demo_block(db), timeout=85)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Demo refresh unavailable: {}", type(exc).__name__)
        return {"status": "unavailable"}
