"""Guard against silently committing an incompletely scored block."""
import pytest
from src.ingest.worker import require_complete_normalization


def test_normalization_rejects_missing_transactions():
    with pytest.raises(ValueError, match="Incomplete block normalization"):
        require_complete_normalization([{"hash": "x"}], [])


def test_normalization_rejects_duplicate_hashes():
    tx = {"hash": "0x" + "a" * 64}
    with pytest.raises(ValueError, match="duplicate"):
        require_complete_normalization([tx, tx], [tx, tx])


@pytest.mark.asyncio
async def test_scoring_failure_rejects_block_before_score_persistence():
    """A scoring exception must escape to the loop's transactional caller."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from src.ingest.worker import process_one_block

    hash_value = "0x" + "a" * 64
    block_hash = "0x" + "b" * 64
    sender = "0x" + "1" * 40
    recipient = "0x" + "2" * 40
    tx = {
        "hash": hash_value,
        "from_address": sender,
        "to_address": recipient,
        "value": "0",
        "block_number": 100,
    }
    raw = {"blockNumber": 100, "blockHash": block_hash}
    block = {"number": 100, "hash": block_hash, "transactions": [raw]}
    normalizer = MagicMock()
    normalizer.normalize_batch.return_value = [tx]
    addresses = MagicMock()
    addresses.bulk_get_or_create_addresses = AsyncMock(return_value={
        sender: 1, recipient: 2, sender.lower(): 1, recipient.lower(): 2
    })
    addresses.get_blacklisted_set = AsyncMock(return_value=set())
    addresses.get_verified_matches = AsyncMock(return_value={})
    transactions = MagicMock()
    transactions.bulk_create_transactions = AsyncMock(return_value=1)
    transactions.bulk_update_risk_scores = AsyncMock()
    scorer = MagicMock()
    scorer.score_transaction = AsyncMock(side_effect=ValueError("injected scoring failure"))

    with patch("src.ingest.worker.load_recent_activity", new_callable=AsyncMock, return_value={}), \
         patch("src.ingest.worker.analyze_block_behavior", return_value={}):
        with pytest.raises(RuntimeError, match="Incomplete block risk scoring"):
            await process_one_block(
                client=MagicMock(), normalizer=normalizer,
                transactions=transactions, addresses=addresses,
                scorer=scorer, explainer=MagicMock(),
                block_number=100, prefetched_block=block,
                allow_external_ai=False,
            )

    transactions.bulk_update_risk_scores.assert_not_awaited()
