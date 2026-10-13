"""Read-only comparison of retained transaction hashes with Ethereum mainnet.

Run: python -m src.ingest.audit_canonical
Optional: CHAIN_AUDIT_BLOCKS=5 (bounded to 1..20)
No SQL writes, checkpoint changes, or automatic rollback.
"""
import asyncio
import json
import os
from src.blockchain.client import BlockchainClient
from src.database.connection import get_db, close_db
from src.ingest.cursor import load_cursor_checkpoint


def as_hash(value):
    if hasattr(value, "hex"):
        value = value.hex()
    value = str(value)
    return (value if value.startswith("0x") else "0x" + value).lower()


async def main():
    limit = max(1, min(20, int(os.getenv("CHAIN_AUDIT_BLOCKS", "5"))))
    client = BlockchainClient()
    if not await client.connect():
        raise RuntimeError("Ethereum mainnet RPC unavailable")
    try:
        db = await get_db()
        height, saved_hash = await load_cursor_checkpoint(db)
        if height is None or not saved_hash:
            raise RuntimeError("Checkpoint height and hash required for audit")
        bounds = await db.fetchrow(
            "SELECT MIN(block_number) AS first_block, MAX(block_number) AS last_block, "
            "COUNT(*) AS tx_count FROM transactions"
        )
        print("audit_mode=read_only")
        canonical_checkpoint = await client.get_block(height, full_transactions=False)
        canonical_checkpoint_hash = as_hash(canonical_checkpoint["hash"])
        checkpoint_matches = as_hash(saved_hash) == canonical_checkpoint_hash
        print(f"checkpoint={height} saved_hash={saved_hash}")
        print(f"checkpoint_canonical_hash={canonical_checkpoint_hash} matches={checkpoint_matches}")
        print(f"retained_count={bounds['tx_count']} retained_first={bounds['first_block']} "
              f"retained_last={bounds['last_block']}")
        # Audit the most recent retained heights, including the checkpoint.
        heights = await db.fetch(
            "SELECT block_number, COUNT(*) AS n FROM transactions "
            "WHERE block_number <= $1 GROUP BY block_number "
            "ORDER BY block_number DESC LIMIT $2", height, limit
        )
        audit_rows = []
        for row in heights:
            block_height = int(row["block_number"])
            stored = await db.fetch(
                "SELECT hash FROM transactions WHERE block_number = $1", block_height
            )
            canonical = await client.get_block(block_height, full_transactions=False)
            canonical_hashes = {as_hash(h) for h in canonical["transactions"]}
            stored_hashes = {as_hash(item["hash"]) for item in stored}
            missing = stored_hashes - canonical_hashes
            audit_rows.append({
                'block_number': block_height,
                'canonical_block_hash': as_hash(canonical['hash']),
                'retained_transactions': len(stored_hashes),
                'canonical_transactions': len(canonical_hashes),
                'noncanonical_retained_count': len(missing),
                'noncanonical_retained_sample': sorted(missing)[:3],
                'retained_membership_matches_canonical': len(missing) == 0,
            })
            print(
                f"block={block_height} canonical_hash={as_hash(canonical['hash'])} "
                f"stored={len(stored_hashes)} canonical_tx_count={len(canonical_hashes)} "
                f"noncanonical_stored={len(missing)} "
                f"sample_noncanonical={','.join(sorted(missing)[:3]) or 'none'}"
            )
        assessment = {
            "mode": "read_only",
            "checkpoint_height": height,
            "saved_checkpoint_hash": as_hash(saved_hash),
            "canonical_checkpoint_hash": canonical_checkpoint_hash,
            "checkpoint_matches": checkpoint_matches,
            "audited_retained_blocks": audit_rows,
            "repair_approved": False,
            "safe_replay_anchor_established": False,
            "warning": "Retained transaction membership alone cannot prove a safe rollback anchor. No writes, checkpoint changes, or replay were performed.",
        }
        print("AUDIT_JSON=" + json.dumps(assessment, sort_keys=True))
        print("result=inspection_only_backup_and_explicit_approval_required_for_repair")
    finally:
        await client.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
