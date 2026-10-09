"""
Ingest worker — a single iteration of the ingest pipeline.

Fetches the latest Ethereum block, stores transactions, scores them
for risk, and generates AI explanations for flagged transactions.

Instrumented with Prometheus metrics.
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

from src.metrics import (
    ingest_blocks_total,
    ingest_transactions_total,
    ingest_errors_total,
    ingest_iteration_duration_seconds,
    risk_scored_total,
    risk_flagged_total,
)
from src.metrics.registry import timer


async def process_one_block(
    client: BlockchainClient,
    normalizer: TransactionNormalizer,
    transactions: TransactionRepository,
    addresses: AddressRepository,
    scorer,
    explainer,
) -> Dict:
    """Fetch the latest Ethereum block and process it end-to-end."""
    start_time = time.time()

    with timer(ingest_iteration_duration_seconds):
        # 1. Get latest block
        block_number = await client.get_latest_block_number()
        block = await client.get_block(block_number, full_transactions=True)
        raw_txs = [dict(tx) for tx in block.get('transactions', [])]

        # 2. Normalize
        normalized = normalizer.normalize_batch(raw_txs, block)

        # 3. Store + score + explain
        inserted = 0
        flagged = 0
        explained = 0
        errors = 0

        for tx in normalized:
            try:
                await transactions.create(tx)
                inserted += 1
                ingest_transactions_total.inc()

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
                risk_scored_total.inc()

                if result['score'] >= 20:
                    flagged += 1
                    risk_flagged_total.inc()
                    explanation = await explainer.explain(tx, result['factors'])
                    if explanation:
                        await transactions.update_explanation(tx['hash'], explanation)
                        explained += 1

            except Exception as e:
                errors += 1
                ingest_errors_total.labels(error_type=type(e).__name__).inc()
                if errors <= 3:
                    logger.warning(f"Transaction error {tx.get('hash', '?')[:20]}: {e}")

        ingest_blocks_total.inc()

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
    """One-shot invocation: connect, process one block, disconnect."""
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