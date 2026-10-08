"""
Ingest worker — a single iteration of the ingest pipeline.

This module does one thing: fetch the latest Ethereum block, store
its transactions, score them for risk, and explain flagged ones.

It does NOT loop — that's `loop.py`'s job.
"""
import time
from typing import Dict
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.connection import get_db, close_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.risk.scorer import get_scorer
from src.agents.explainer import get_explainer


async def process_one_block(
    client: BlockchainClient,
    normalizer: TransactionNormalizer,
    transactions: TransactionRepository,
    addresses: AddressRepository,
    scorer,
    explainer,
) -> Dict:
    """
    Fetch the latest Ethereum block and process it end-to-end.

    Returns a summary dict with stats for logging.
    """
    start_time = time.time()

    # 1. Get latest block
    block_number = await client.get_latest_block_number()
    block = await client.get_block(block_number, full_transactions=True)
    raw_txs = [dict(tx) for tx in block.get('transactions', [])]

    # 2. Normalize
    normalized = normalizer.normalize_batch(raw_txs, block)

    # 3. Store + score + explain each transaction
    inserted = 0
    flagged = 0
    explained = 0
    errors = 0

    for tx in normalized:
        try:
            # Store (idempotent — skips duplicates via ON CONFLICT)
            await transactions.create(tx)
            inserted += 1

            # Score for risk
            is_blacklisted = await addresses.is_blacklisted(tx['to_address'])
            result = await scorer.score_transaction(
                tx=tx,
                address_history=[],
                is_blacklisted=is_blacklisted,
            )

            await transactions.update_risk(
                tx['hash'],
                result['score'],
                result['factors'],
            )

            # Explain if flagged
            if result['score'] >= 20:
                flagged += 1
                explanation = await explainer.explain(tx, result['factors'])
                if explanation:
                    await transactions.update_explanation(tx['hash'], explanation)
                    explained += 1

        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.warning(f"Transaction error {tx.get('hash', '?')[:20]}: {e}")

    elapsed = time.time() - start_time

    return {
        'block_number': block_number,
        'total_transactions': len(normalized),
        'inserted': inserted,
        'flagged': flagged,
        'explained': explained,
        'errors': errors,
        'elapsed_seconds': round(elapsed, 2),
    }


async def run_once() -> Dict:
    """
    One-shot invocation: connect, process one block, disconnect.
    Used for testing.
    """
    client = BlockchainClient()
    await client.connect()

    db = await get_db()
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()

    try:
        summary = await process_one_block(
            client, normalizer, transactions, addresses, scorer, explainer
        )
        return summary
    finally:
        await client.close()
        await close_db()


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_once())
    print(f"\n✅ Summary: {result}\n")