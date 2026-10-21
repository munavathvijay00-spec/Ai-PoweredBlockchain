"""Free-tier storage policy for ChainScope.

The live database is not an Ethereum archive. It keeps only a very small recent
window for monitoring and a bounded, normalized cache for investigated wallets.
Deep history remains provider-backed and can be re-fetched on demand.
"""

import os


def bounded_retention_minutes(value: str | None) -> int:
    """Reject unsafe settings rather than silently expanding the hot database."""
    if value is None or not value.strip():
        return 5
    try:
        minutes = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("CHAINSCOPE_LIVE_RETENTION_MINUTES must be an integer") from exc
    if not 5 <= minutes <= 60:
        raise ValueError("Live retention must remain within the 5–60 minute safety range")
    return minutes


# This governs the monitoring hot table, not durable investigation evidence.
# Longer retention requires a measured PostgreSQL capacity and recovery plan.
LIVE_RETENTION_MINUTES = bounded_retention_minutes(os.getenv("CHAINSCOPE_LIVE_RETENTION_MINUTES"))
LINEAGE_RETENTION_BLOCKS = 128
HISTORY_MAX_ROWS_PER_WALLET = 2_500
HISTORY_MAX_WALLETS = 10
HISTORY_MAX_ROWS_GLOBAL = HISTORY_MAX_ROWS_PER_WALLET * HISTORY_MAX_WALLETS


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


def _command_count(result: str) -> int:
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (AttributeError, ValueError):
        return 0


async def prune_historical_evidence(db, wallet: str) -> dict:
    """Bound persistent historical cache without misreporting completeness.

    Each investigated wallet keeps a compact recent slice. If more wallets are
    investigated than the free-tier budget allows, the least recently synced
    wallets are evicted as whole cache entries. Their provider history remains
    re-fetchable later.
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
    wallet_count = _command_count(deleted_wallet)

    if wallet_count:
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

    evicted_wallets = await db.fetch(
        """
        SELECT wallet_address
        FROM wallet_history_sync
        WHERE chain_id = 1
        ORDER BY updated_at DESC, wallet_address
        OFFSET $1
        """,
        HISTORY_MAX_WALLETS,
    )
    evicted_addresses = [row["wallet_address"] for row in evicted_wallets]
    evicted_rows = 0
    if evicted_addresses:
        result = await db.execute(
            """
            DELETE FROM wallet_transfer_evidence
            WHERE chain_id = 1 AND wallet_address = ANY($1::varchar[])
            """,
            evicted_addresses,
        )
        evicted_rows = _command_count(result)
        await db.execute(
            """
            DELETE FROM wallet_history_sync
            WHERE chain_id = 1 AND wallet_address = ANY($1::varchar[])
            """,
            evicted_addresses,
        )

    return {
        "wallet_deleted": wallet_count,
        "evicted_wallets": len(evicted_addresses),
        "evicted_rows": evicted_rows,
    }
