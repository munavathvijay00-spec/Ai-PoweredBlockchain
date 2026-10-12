"""Truthful observed-data coverage, never presented as full Ethereum history."""
from fastapi import APIRouter, Depends

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository

router = APIRouter(prefix="/api", tags=["data coverage"])


@router.get("/coverage")
async def get_coverage(repo: TransactionRepository = Depends(get_transaction_repo)):
    stats = await repo.db.fetchrow("""
        SELECT MIN(block_number) AS min_block, MAX(block_number) AS max_block,
               MIN(timestamp) AS oldest_observed_at, MAX(timestamp) AS newest_observed_at,
               COUNT(*) AS stored_transactions,
               COUNT(DISTINCT block_number) AS blocks_with_stored_transactions
        FROM transactions
    """)
    return {
        "chain_id": 1,
        "network": "ethereum-mainnet",
        "native_transactions": {
            "status": "partial_recent_retained",
            "stored_transactions": stats["stored_transactions"],
            "min_observed_block": stats["min_block"],
            "max_observed_block": stats["max_block"],
            "blocks_with_stored_transactions": stats["blocks_with_stored_transactions"],
            "oldest_observed_at": stats["oldest_observed_at"],
            "newest_observed_at": stats["newest_observed_at"],
            "historical_completeness": False,
            "note": "Worker starts at chain tip on first run and currently deletes transactions older than 30 minutes. Observed block bounds do not prove contiguous coverage.",
        },
        "token_events": {"status": "on_demand_only", "historical_completeness": False},
        "internal_traces": {"status": "not_indexed", "historical_completeness": False},
        "reorg_verification": {"status": "not_verified"},
        "wallet_history": {"status": "sampled_from_retained_native_transactions", "historical_completeness": False},
        "limitations": [
            "No complete address-indexed Ethereum history is available from this database.",
            "No guarantee that all blocks between observed minimum and maximum were indexed.",
            "An empty wallet result does not imply an inactive wallet.",
        ],
    }
