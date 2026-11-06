"""Explicitly audited skip of expired live-window block history.

On free-tier instances, a restarted worker can be tens of thousands of blocks
behind. Crawling old block *headers* makes the live 5-minute table permanently
empty, even though those blocks' transactions would be immediately discarded.

Only skip when the target anchor itself is certainly outside the live retention
window, after the ingest loop verified the saved checkpoint is canonical.
Skipped heights are written to a durable gap ledger in the same transaction
that advances the checkpoint. No skipped range is ever described as ingested.
"""
from __future__ import annotations

from src.ingest.cursor import save_cursor_checkpoint
from src.ingest.reorg import block_hash, record_lineage
from src.storage_budget import LIVE_RETENTION_MINUTES

# Ethereum mainnet target: leave about seven minutes between anchor and tip.
# The timestamp check, not this estimate, is the actual safety guard.
ANCHOR_BEHIND_HEAD_BLOCKS = 36
MIN_BACKLOG_BLOCKS = 256


def choose_expired_anchor(checkpoint: int | None, head: int) -> int | None:
    """Never jump for ordinary short restarts or tip fluctuations."""
    if checkpoint is None or checkpoint < 0 or head < 0:
        return None
    if head - checkpoint < MIN_BACKLOG_BLOCKS:
        return None
    target = head - ANCHOR_BEHIND_HEAD_BLOCKS
    return target if target > checkpoint + 1 else None


async def ensure_gap_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ingest_coverage_gaps (
            id BIGSERIAL PRIMARY KEY,
            stream TEXT NOT NULL,
            first_unprocessed_block BIGINT NOT NULL,
            last_unprocessed_block BIGINT NOT NULL,
            anchor_block BIGINT NOT NULL,
            anchor_hash VARCHAR(66) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (last_unprocessed_block >= first_unprocessed_block),
            CHECK (anchor_block = last_unprocessed_block + 1)
        )
    """)


async def jump_past_expired_history(
    db, client, checkpoint: int, head: int,
    *, is_expired,
) -> tuple[int, str] | None:
    """Re-anchor at a provider-verified expired block with an atomic gap audit.

    Caller MUST first compare the existing checkpoint hash to the canonical RPC
    block. Non-contiguous history is not presented as continuously verified.
    """
    target = choose_expired_anchor(checkpoint, head)
    if target is None:
        return None

    anchor = await client.get_block(target, full_transactions=False)
    if not is_expired(anchor, retention_minutes=LIVE_RETENTION_MINUTES):
        return None

    parent = await client.get_block(target - 1, full_transactions=False)
    canonical_hash = block_hash(anchor["hash"])
    if block_hash(anchor["parentHash"]) != block_hash(parent["hash"]):
        raise RuntimeError("LINEAGE_CONFLICT: provider returned inconsistent catch-up anchor")

    async with db.transaction():
        await ensure_gap_schema(db)
        await db.execute("""
            INSERT INTO ingest_coverage_gaps
                (stream, first_unprocessed_block, last_unprocessed_block,
                 anchor_block, anchor_hash, reason)
            VALUES ('ethereum_mainnet', $1, $2, $3, $4, $5)
        """, checkpoint + 1, target - 1, target, canonical_hash,
             "Expired live-window history skipped during free-tier recovery; not indexed.")
        # Hash-anchored lineage starts here; no ancestor-contiguity claim.
        await record_lineage(db, anchor)
        await save_cursor_checkpoint(db, target, canonical_hash)
    return target, canonical_hash
