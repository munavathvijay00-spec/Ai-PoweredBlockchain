"""Recover only an independently verified checkpoint advanced by a competing worker.

Render rolling deployments can overlap old and new API instances briefly.
A checkpoint compare-and-swap conflict must remain fail-closed unless the
persisted winner is strictly newer and its hash matches the canonical RPC.
"""
from src.ingest.cursor import load_cursor_checkpoint
from src.ingest.reorg import block_hash


async def reconcile_competing_worker(db, client, previous_height: int):
    saved_height, saved_hash = await load_cursor_checkpoint(db)
    if saved_height is None or saved_height <= previous_height or not saved_hash:
        return None
    canonical = await client.get_block(saved_height, full_transactions=False)
    if block_hash(canonical["hash"]) != saved_hash.lower():
        raise RuntimeError("LINEAGE_CONFLICT: competing checkpoint not canonical")
    if int(canonical["number"]) != saved_height:
        raise RuntimeError("LINEAGE_CONFLICT: inconsistent checkpoint block height")
    return saved_height, saved_hash.lower()
