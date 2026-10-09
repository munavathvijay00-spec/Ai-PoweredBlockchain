"""
Ingest worker — one iteration of the ingest pipeline.
Optimized with bulk DB operations.
"""
import asyncio
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
    """Fetch the latest block, store transactions using bulk ops, score + explain."""
    start_time = time.time()

    with timer(ingest_iteration_duration_seconds):
        # 1. Fetch block
        block_number = await client.get_latest_block_number()
        block = await client.get_block(block_number, full_transactions=True)
        raw_txs = [dict(tx) for tx in block.get('transactions', [])]

        # 2. Normalize
        normalized = normalizer.normalize_batch(raw_txs, block)

        # 3. Collect unique addresses
        all_addresses = set()
        for tx in normalized:
            all_addresses.add(tx['from_address'])
            all_addresses.add(tx['to_address'])
        addresses_list = list(all_addresses)

        # 4. Bulk insert addresses (1 query)
        addr_map = await addresses.bulk_get_or_create_addresses(addresses_list)

        # 5. Bulk insert transactions (1 query)
        inserted = await transactions.bulk_create_transactions(normalized, addr_map)
        if inserted:
            ingest_transactions_total.inc(inserted)

        # 6. Bulk fetch blacklist (1 query)
        blacklist_set = await addresses.get_blacklisted_set(addresses_list)

        # 7. Score in-memory
        scores = []
        flagged = 0
        for tx in normalized:
            try:
                is_black = (
                    tx['to_address'].lower() in blacklist_set or
                    tx['from_address'].lower() in blacklist_set
                )
                result = await scorer.score_transaction(
                    tx=tx,
                    address_history=[],
                    is_blacklisted=is_black,
                )
                scores.append({
                    'hash': tx['hash'],
                    'score': result['score'],
                    'factors': result['factors'],
                })
                risk_scored_total.inc()
                if result['score'] >= 20:
                    flagged += 1
                    risk_flagged_total.inc()
            except Exception as e:
                ingest_errors_total.labels(error_type=type(e).__name__).inc()
                logger.warning(f"Scoring error {tx.get('hash', '?')[:20]}: {e}")

        # 8. Bulk update risk scores (1 query)
        if scores:
            await transactions.bulk_update_risk_scores(scores)

        # 9. Explain flagged in parallel
        explained = 0
        flagged_scores = [s for s in scores if s['score'] >= 20]
        if flagged_scores:
            tx_by_hash = {tx['hash']: tx for tx in normalized}
            tasks = []
            for s in flagged_scores:
                tx = tx_by_hash.get(s['hash'])
                if tx:
                    tasks.append(explainer.explain(tx, s['factors']))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            to_save = []
            for s, result in zip(flagged_scores, results):
                if isinstance(result, str) and result:
                    to_save.append({
                        'hash': s['hash'],
                        'explanation': result,
                    })
                    explained += 1
                elif isinstance(result, Exception):
                    logger.warning(f"Explain error {s['hash'][:20]}: {result}")

            if to_save:
                await transactions.bulk_update_explanations(to_save)

        ingest_blocks_total.inc()
        elapsed = time.time() - start_time

        return {
            'block_number': block_number,
            'total_transactions': len(normalized),
            'inserted': inserted,
            'flagged': flagged,
            'explained': explained,
            'errors': 0,
            'elapsed_seconds': round(elapsed, 2),
        }


async def run_once() -> Dict:
    """One-shot invocation."""
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
    result = asyncio.run(run_once())
    print(f"\n✅ Summary: {result}\n")