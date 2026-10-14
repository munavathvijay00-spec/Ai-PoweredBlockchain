"""Bounded, fail-closed Ethereum reorg recovery.

Normal Ethereum reorgs are usually shallow. ChainScope automatically rewinds only
when it can verify a common canonical ancestor using durable block lineage or an
exact transaction-membership comparison. If verification is unavailable or the
fork is deeper than the configured bound, ingestion still halts for manual review.
"""
from dataclasses import dataclass
from loguru import logger

from src.blockchain.normalizer import TransactionNormalizer
from src.ingest.cursor import rewind_cursor_checkpoint, validate_block_hash
from src.metrics import ingest_integrity_halts_total


@dataclass(frozen=True)
class ReorgRecovery:
    ancestor_block: int
    ancestor_hash: str
    depth: int
    deleted_transactions: int
    verification: str


def block_hash(value) -> str:
    value = value.hex() if hasattr(value, "hex") else str(value)
    result = value if value.startswith("0x") else "0x" + value
    result = result.lower()
    validate_block_hash(result)
    return result


def transaction_hashes(block) -> set[str]:
    hashes = set()
    for tx in block.get("transactions", []):
        raw = tx.get("hash") if hasattr(tx, "get") else None
        if raw is None:
            raise ValueError("Canonical block transaction missing hash")
        value = TransactionNormalizer._to_hex_string(raw).lower()
        if len(value) != 66:
            raise ValueError("Canonical block contains invalid transaction hash")
        hashes.add(value)
    if len(hashes) != len(block.get("transactions", [])):
        raise ValueError("Canonical block contains duplicate transaction hash")
    return hashes


async def ensure_lineage_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ingest_block_lineage (
            block_number BIGINT PRIMARY KEY,
            block_hash VARCHAR(66) NOT NULL,
            parent_hash VARCHAR(66) NOT NULL,
            transaction_count INTEGER NOT NULL CHECK (transaction_count >= 0),
            committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(block_hash)
        )
    """)


async def record_lineage(db, block) -> None:
    height = int(block["number"])
    canonical_hash = block_hash(block["hash"])
    parent_hash = block_hash(block["parentHash"])
    tx_count = len(block.get("transactions", []))
    await db.execute("""
        INSERT INTO ingest_block_lineage
            (block_number, block_hash, parent_hash, transaction_count, committed_at)
        VALUES ($1,$2,$3,$4,NOW())
        ON CONFLICT (block_number) DO UPDATE SET
            block_hash=EXCLUDED.block_hash,
            parent_hash=EXCLUDED.parent_hash,
            transaction_count=EXCLUDED.transaction_count,
            committed_at=NOW()
        WHERE ingest_block_lineage.block_hash = EXCLUDED.block_hash
    """, height, canonical_hash, parent_hash, tx_count)
    row = await db.fetchrow(
        "SELECT block_hash,parent_hash,transaction_count FROM ingest_block_lineage WHERE block_number=$1",
        height,
    )
    if (
        not row
        or row["block_hash"].lower() != canonical_hash
        or row["parent_hash"].lower() != parent_hash
        or int(row["transaction_count"]) != tx_count
    ):
        raise RuntimeError("LINEAGE_CONFLICT: block height already has contradictory canonical lineage")


async def _stored_hashes(db, height: int) -> set[str]:
    rows = await db.fetch(
        "SELECT lower(hash) AS hash FROM transactions WHERE block_number=$1 ORDER BY hash",
        height,
    )
    return {row["hash"] for row in rows}


async def _verified_common_ancestor(db, client, checkpoint: int, max_depth: int):
    """Find a common ancestor below a mismatched checkpoint.

    Prefer persisted block hashes. During first deployment of lineage tracking,
    fall back to exact retained transaction membership. Empty-block membership is
    not sufficient as a bootstrap proof because two competing blocks can both be
    empty, so that case remains fail-closed unless lineage exists.
    """
    floor = max(0, checkpoint - max_depth)
    for height in range(checkpoint - 1, floor - 1, -1):
        canonical = await client.get_block(height, full_transactions=True)
        canonical_hash = block_hash(canonical["hash"])
        lineage = await db.fetchrow(
            "SELECT block_hash, transaction_count FROM ingest_block_lineage WHERE block_number=$1",
            height,
        )
        if lineage:
            if lineage["block_hash"].lower() == canonical_hash:
                return height, canonical_hash, "lineage_hash"
            continue

        canonical_hashes = transaction_hashes(canonical)
        if not canonical_hashes:
            continue
        stored_hashes = await _stored_hashes(db, height)
        if stored_hashes == canonical_hashes:
            return height, canonical_hash, "exact_transaction_membership"
    return None


async def recover_shallow_reorg(
    db,
    client,
    *,
    checkpoint_block: int,
    checkpoint_hash: str,
    max_depth: int = 12,
) -> ReorgRecovery:
    """Verify ancestor, atomically remove orphaned evidence, and rewind cursor."""
    if max_depth < 1 or max_depth > 64:
        raise ValueError("max_depth must be between 1 and 64")
    validate_block_hash(checkpoint_hash)
    await ensure_lineage_schema(db)
    ancestor = await _verified_common_ancestor(db, client, checkpoint_block, max_depth)
    if ancestor is None:
        ingest_integrity_halts_total.labels(reason="reorg_no_verified_ancestor").inc()
        raise RuntimeError(
            f"REORG_DETECTED: no verified common ancestor within {max_depth} blocks; manual recovery required"
        )
    ancestor_block, ancestor_hash, verification = ancestor
    depth = checkpoint_block - ancestor_block
    deleted_transactions = 0

    async with db.transaction():
        # Delete known transaction dependants first. Any unknown restrictive FK will
        # abort the transaction, which is safer than leaving mixed orphan evidence.
        alerts_exists = await db.fetchval("SELECT to_regclass('alerts') IS NOT NULL")
        if alerts_exists:
            await db.execute("""
                DELETE FROM alerts
                WHERE transaction_id IN (
                    SELECT id FROM transactions WHERE block_number > $1
                )
            """, ancestor_block)

        history_exists = await db.fetchval(
            "SELECT to_regclass('wallet_transfer_evidence') IS NOT NULL"
        )
        if history_exists:
            await db.execute(
                "DELETE FROM wallet_transfer_evidence WHERE block_number > $1",
                ancestor_block,
            )

        result = await db.execute(
            "DELETE FROM transactions WHERE block_number > $1",
            ancestor_block,
        )
        try:
            deleted_transactions = int(result.rsplit(" ", 1)[-1])
        except (ValueError, AttributeError):
            deleted_transactions = 0

        await db.execute(
            "DELETE FROM ingest_block_lineage WHERE block_number > $1",
            ancestor_block,
        )
        await rewind_cursor_checkpoint(
            db,
            expected_block=checkpoint_block,
            expected_hash=checkpoint_hash,
            ancestor_block=ancestor_block,
            ancestor_hash=ancestor_hash,
        )
        # Persist the verified ancestor so subsequent reorg recovery no longer
        # needs the transaction-membership bootstrap path.
        canonical_ancestor = await client.get_block(ancestor_block, full_transactions=True)
        await record_lineage(db, canonical_ancestor)

    logger.warning(
        "Canonical reorg recovered: checkpoint={} ancestor={} depth={} tx_deleted={} verification={}",
        checkpoint_block,
        ancestor_block,
        depth,
        deleted_transactions,
        verification,
    )
    return ReorgRecovery(
        ancestor_block=ancestor_block,
        ancestor_hash=ancestor_hash,
        depth=depth,
        deleted_transactions=deleted_transactions,
        verification=verification,
    )
