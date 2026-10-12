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
from src.risk.behavior import analyze_block_behavior, apply_behavior_risk
from src.agents.explainer import get_explainer, evidence_explanation
from src.risk.ofac_intelligence import ensure_intelligence_schema, refresh_ofac
from src.risk.wallet_exposure import (ensure_exposure_schema, find_direct_exposures, save_direct_exposures,
                                      get_direct_exposures, apply_exposure_risk)

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
    block_number: int | None = None,
) -> Dict:
    """Fetch the latest block, store transactions using bulk ops, score + explain."""
    start_time = time.time()

    with timer(ingest_iteration_duration_seconds):
        # 1. Fetch block
        if block_number is None:
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
        verified_matches = await addresses.get_verified_matches(addresses_list)
        # Only evidence from observed transactions; persisted for at most seven days.
        try:
            await save_direct_exposures(addresses.db, find_direct_exposures(normalized, verified_matches))
        except Exception as exposure_err:
            logger.warning(f'Direct exposure persistence unavailable: {exposure_err}')
        exposure_matches = await get_direct_exposures(addresses.db, addresses_list)

        # Same-block evidence only: no expensive historical scans or new DB tables.
        behavior_factors = analyze_block_behavior(normalized)

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
                # Add independently verifiable source evidence, not an AI claim.
                matched = [verified_matches[a.lower()] for a in
                           (tx['from_address'], tx['to_address']) if a.lower() in verified_matches]
                if matched:
                    result['factors'] = [f for f in result['factors'] if f['factor'] != 'blacklisted_address']
                    for evidence in matched:
                        result['factors'].append({
                            'factor': 'verified_sanctions_match',
                            'points': 100,
                            'reason': 'Exact Ethereum address match in OFAC SDN sanctions data',
                            'source': evidence['source'],
                            'address': evidence['address'],
                            'entity_id': evidence['entity_id'],
                            'entity_name': evidence['entity_name'],
                            'checked_at': evidence['checked_at'].isoformat(),
                        })
                result = apply_exposure_risk(result, tx, exposure_matches, verified_matches)
                result = apply_behavior_risk(result, tx, behavior_factors)
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

        # 9. Every flagged transaction receives an evidence-based explanation.
        # Only the three highest-risk items request AI wording, preserving cost.
        flagged_scores = sorted(
            (item for item in scores if item['score'] >= 20),
            key=lambda item: item['score'], reverse=True,
        )
        tx_by_hash = {tx['hash']: tx for tx in normalized}
        to_save = []
        for item in flagged_scores:
            tx = tx_by_hash.get(item['hash'])
            if tx:
                to_save.append({
                    'hash': item['hash'],
                    'explanation': evidence_explanation(
                        {**tx, 'risk_score': item['score']}, item['factors']
                    ),
                })

        ai_candidates = flagged_scores[:3]
        tasks = []
        task_scores = []
        for item in ai_candidates:
            tx = tx_by_hash.get(item['hash'])
            if tx:
                tasks.append(explainer.explain(
                    {**tx, 'risk_score': item['score']}, item['factors']
                ))
                task_scores.append(item)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            overrides = {}
            for item, result in zip(task_scores, results):
                if isinstance(result, str) and result:
                    overrides[item['hash']] = result
                elif isinstance(result, Exception):
                    logger.warning(f"Explain error {item['hash'][:20]}: {result}")
            for row in to_save:
                if row['hash'] in overrides:
                    row['explanation'] = overrides[row['hash']]

        if to_save:
            await transactions.bulk_update_explanations(to_save)
        explained = len(to_save)

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
    await ensure_intelligence_schema(db)
    await ensure_exposure_schema(db)
    await refresh_ofac(db)
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