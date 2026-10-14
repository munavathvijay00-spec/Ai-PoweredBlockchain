"""Free-tier storage policy for ChainScope.

The live database is not an Ethereum archive. It keeps only a very small recent
window for monitoring and a bounded, normalized cache for investigated wallets.
Deep history remains provider-backed and can be re-fetched on demand.
"""

LIVE_RETENTION_MINUTES = 5
LINEAGE_RETENTION_BLOCKS = 128
HISTORY_MAX_ROWS_PER_WALLET = 2_500
HISTORY_MAX_ROWS_GLOBAL = 25_000


def lineage_floor(checkpoint_block: int | None) -> int | None:
    if checkpoint_block is None:
        return None
    return max(0, int(checkpoint_block) - LINEAGE_RETENTION_BLOCKS)


async def prune_lineage(db, checkpoint_block: int | None) -> int:
    """Keep enough canonical lineage for bounded reorg recovery plus headroom."""
    floor = lineage_floor(checkpoint_block)
    if floor is None:
        return 0
    result = await db.execute(
        "DELETE FROM ingest_block_lineage WHERE block_number < $1",
        floor,
    )
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (AttributeError, ValueError):
        return 0


async def prune_historical_evidence(db, wallet: str) -> dict:
    """Bound persistent historical cache without pretending provider history vanished.

    The normalized cache is only an acceleration layer. Removed rows can be
    re-fetched from the provider later; provider pagination state/completeness is
    therefore reset whenever pruning occurs.
    """
    wallet = wallet.lower()
    deleted_wallet = await db.execute(
        """
        DELETE FROM wallet_transfer_evidence
        WHERE ctid IN (
            SELECT ctid
            FROM wallet_transfer_evidence
            WHERE chain_id = 1 AND wallet_address = $1
            ORDER BY block_number DESC NULLS LAST, observed_at DESC
            OFFSET $2
        )
        """,
        wallet,
        HISTORY_MAX_ROWS_PER_WALLET,
    )

    deleted_global = await db.execute(
        """
        DELETE FROM wallet_transfer_evidence
        WHERE ctid IN (
            SELECT ctid
            FROM wallet_transfer_evidence
            ORDER BY observed_at DESC
            OFFSET $1
        )
        """,
        HISTORY_MAX_ROWS_GLOBAL,
    )

    def _count(result: str) -> int:
        try:
            return int(result.rsplit(" ", 1)[-1])
        except (AttributeError, ValueError):
            return 0

    wallet_count = _count(deleted_wallet)
    global_count = _count(deleted_global)
    if wallet_count or global_count:
        await db.execute(
            """
            UPDATE wallet_history_sync
            SET outgoing_complete = FALSE,
                incoming_complete = FALSE,
                outgoing_page_key = NULL,
                incoming_page_key = NULL,
                records_cached = (
                    SELECT COUNT(*) FROM wallet_transfer_evidence
                    WHERE chain_id = 1 AND wallet_address = $1
                ),
                updated_at = NOW()
            WHERE chain_id = 1 AND wallet_address = $1
            """,
            wallet,
        )
    return {"wallet_deleted": wallet_count, "global_deleted": global_count}
