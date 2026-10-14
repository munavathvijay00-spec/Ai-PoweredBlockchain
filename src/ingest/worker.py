"""Ingest worker — one atomic canonical block through normalization, scoring, and storage."""
import asyncio
import time
from typing import Dict
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.blockchain.normalizer import TransactionNormalizer
from src.database.connection import get_db, close_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.risk.scorer import get_scorer
from src.risk.evidence_v2 import assess_evidence
from src.risk.behavior import analyze_block_behavior, apply_behavior_risk
from src.risk.history_context import load_recent_activity
from src.agents.explainer import get_explainer, evidence_explanation

from src.metrics import (
    ingest_blocks_total,
    ingest_transactions_total,
    ingest_errors_total,
    ingest_iteration_duration_seconds,
    ingest_last_success_unixtime,
    risk_scored_total,
    risk_flagged_total,
)
from src.metrics.registry import timer


def require_complete_normalization(raw_txs: list, normalized: list) -> None:
    if len(normalized) != len(raw_txs):
        raise ValueError(
            f"Incomplete block normalization: {len(normalized)} of {len(raw_txs)} transactions; refusing checkpoint"
        )
    hashes = [tx.get("hash") for tx in normalized]
    if any(
        not isinstance(h, str)
        or not h.startswith("0x")
        or len(h) != 66
        or any(ch not in "0123456789abcdefABCDEF" for ch in h[2:])
        for h in hashes
    ):
        raise ValueError("Normalized block contains invalid transaction hashes")
    if len(set(hashes)) != len(hashes):
        raise ValueError("Normalized block contains duplicate transaction hashes")


def validate_block_snapshot(block: Dict, expected_number: int) -> None:
    if int(block["number"]) != expected_number:
        raise ValueError("Fetched block height differs from requested height")
    if not isinstance(block.get("transactions"), (list, tuple)):
        raise ValueError("Full transaction block snapshot required")
    if any(not isinstance(tx, dict) and not hasattr(tx, "items") for tx in block["transactions"]):
        raise ValueError("Transaction hashes alone are not a full block snapshot")
    from src.ingest.cursor import validate_block_hash
    if block.get("hash") is None:
        raise ValueError("Canonical block hash missing from full block snapshot")
    block_hash = TransactionNormalizer._to_hex_string(block["hash"]).lower()
    validate_block_hash(block_hash)
    for tx in block["transactions"]:
        tx_number = tx.get("blockNumber")
        if tx_number is None:
            raise ValueError("Transaction block number missing from full block snapshot")
        if int(tx_number) != expected_number:
            raise ValueError("Transaction block number differs from fetched block")
        tx_block_hash = tx.get("blockHash")
        if tx_block_hash is None:
            raise ValueError("Transaction block hash missing from full block snapshot")
        normalized_hash = TransactionNormalizer._to_hex_string(tx_block_hash).lower()
        validate_block_hash(normalized_hash)
        if normalized_hash != block_hash:
            raise ValueError("Transaction block hash differs from fetched block")


async def process_one_block(
    client: BlockchainClient,
    normalizer: TransactionNormalizer,
    transactions: TransactionRepository,
    addresses: AddressRepository,
    scorer,
    explainer,
    block_number: int | None = None,
    prefetched_block: Dict | None = None,
    allow_external_ai: bool = True,
) -> Dict:
    start_time = time.time()
    with timer(ingest_iteration_duration_seconds):
        if block_number is None:
            block_number = await client.get_latest_block_number()
        block = prefetched_block if prefetched_block is not None else await client.get_block(
            block_number, full_transactions=True
        )
        validate_block_snapshot(block, block_number)
        raw_txs = [dict(tx) for tx in block.get("transactions", [])]
        normalized = normalizer.normalize_batch(raw_txs, block)
        require_complete_normalization(raw_txs, normalized)

        all_addresses = set()
        for tx in normalized:
            all_addresses.add(tx["from_address"])
            all_addresses.add(tx["to_address"])
        addresses_list = list(all_addresses)

        addr_map = await addresses.bulk_get_or_create_addresses(addresses_list)
        if any(addr.lower() not in addr_map for addr in addresses_list):
            raise RuntimeError("Incomplete address indexing; refusing to store partial block")

        inserted = await transactions.bulk_create_transactions(normalized, addr_map)
        if inserted:
            ingest_transactions_total.inc(inserted)

        blacklist_set = await addresses.get_blacklisted_set(addresses_list)
        same_block_factors = analyze_block_behavior(normalized)

        recent_activity = await load_recent_activity(
            transactions.db,
            addresses_list,
            before_block=block_number,
            minutes=30,
            per_address=100,
        )

        scores = []
        flagged = 0
        for tx in normalized:
            try:
                is_black = (
                    tx["to_address"].lower() in blacklist_set
                    or tx["from_address"].lower() in blacklist_set
                )
                result = await scorer.score_transaction(
                    tx=tx,
                    address_history=recent_activity.get(tx["from_address"].lower(), []),
                    is_blacklisted=is_black,
                )
                result = apply_behavior_risk(result, tx, same_block_factors)
                scores.append({
                    "hash": tx["hash"],
                    "score": result["score"],
                    "factors": result["factors"],
                })
                risk_scored_total.inc()
                if result["score"] >= 20:
                    flagged += 1
                    risk_flagged_total.inc()
            except Exception as exc:
                ingest_errors_total.labels(error_type=type(exc).__name__).inc()
                logger.warning(f"Scoring error {tx.get('hash', '?')[:20]}: {exc}")

        if scores:
            await transactions.bulk_update_risk_scores(scores)

        flagged_scores = sorted(
            (item for item in scores if item["score"] >= 20),
            key=lambda item: item["score"],
            reverse=True,
        )
        tx_by_hash = {tx["hash"]: tx for tx in normalized}
        to_save = []
        for item in flagged_scores:
            tx = tx_by_hash.get(item["hash"])
            if tx:
                to_save.append({
                    "hash": item["hash"],
                    "explanation": evidence_explanation(
                        {**tx, "risk_score": item["score"]}, item["factors"]
                    ),
                })

        ai_candidates = [
            item for item in flagged_scores
            if assess_evidence(item["factors"], item["hash"])["assessment"] == "review"
        ][:3]
        tasks = []
        task_scores = []
        for item in ai_candidates:
            tx = tx_by_hash.get(item["hash"])
            if tx:
                tasks.append(explainer.explain(
                    {**tx, "risk_score": item["score"]}, item["factors"]
                ))
                task_scores.append(item)

        if tasks and allow_external_ai:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            overrides = {}
            for item, result in zip(task_scores, results):
                if isinstance(result, str) and result:
                    overrides[item["hash"]] = result
                elif isinstance(result, Exception):
                    logger.warning(f"Explain error {item['hash'][:20]}: {result}")
            for row in to_save:
                if row["hash"] in overrides:
                    row["explanation"] = overrides[row["hash"]]

        if to_save:
            await transactions.bulk_update_explanations(to_save)
        explained = len(to_save)

        ingest_blocks_total.inc()
        ingest_last_success_unixtime.set(time.time())
        elapsed = time.time() - start_time
        return {
            "block_number": block_number,
            "total_transactions": len(normalized),
            "inserted": inserted,
            "flagged": flagged,
            "explained": explained,
            "errors": 0,
            "elapsed_seconds": round(elapsed, 2),
        }


async def run_once() -> Dict:
    client = BlockchainClient()
    if not await client.connect():
        await client.close()
        raise RuntimeError("Ethereum mainnet RPC connection failed or returned a non-mainnet chain")
    db = await get_db()
    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    normalizer = TransactionNormalizer()
    scorer = get_scorer()
    explainer = get_explainer()
    try:
        return await process_one_block(client, normalizer, transactions, addresses, scorer, explainer)
    finally:
        await client.close()
        await close_db()


if __name__ == "__main__":
    result = asyncio.run(run_once())
    print(f"\nSummary: {result}\n")
