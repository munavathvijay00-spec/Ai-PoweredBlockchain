"""Read-only Ethereum ingestion checkpoint diagnostics.

Run inside the Railway service or locally with DATABASE_URL and ETHEREUM_RPC_URL:
    python -m scripts.diagnose_ingestion

Never rewrites the cursor or deletes transaction evidence.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

from src.blockchain.client import BlockchainClient
from src.database.connection import get_db, close_db


def normalized_hash(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if hasattr(value, "hex") and not isinstance(value, str):
        value = value.hex()
    value = str(value).lower()
    return value if value.startswith("0x") else "0x" + value


def iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


async def main():
    report = {"status": "unverified", "checks": {}, "recommended_action": None}
    client = BlockchainClient()
    try:
        db = await get_db()
        cursor = await db.fetchrow(
            "SELECT last_block, block_hash, updated_at FROM ingest_cursor WHERE stream = $1",
            "ethereum_mainnet",
        )
        if not cursor:
            report["status"] = "missing_cursor"
            report["recommended_action"] = "Check the ingestion worker startup and cursor initialization logs."
            return report
        height = int(cursor["last_block"])
        expected = normalized_hash(cursor["block_hash"])
        updated = cursor["updated_at"]
        if updated and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        report["checks"]["stored_cursor"] = {
            "height": height,
            "hash": expected,
            "updated_at": iso(updated),
            "age_seconds": int((datetime.now(timezone.utc) - updated).total_seconds()) if updated else None,
        }

        if not await client.connect():
            report["status"] = "rpc_unavailable"
            report["recommended_action"] = "Verify RPC URL, key, Ethereum mainnet chain ID, and network connectivity."
            return report

        tip = await client.get_latest_block_number()
        report["checks"]["rpc_tip"] = tip
        if height > tip:
            report["status"] = "cursor_ahead_of_rpc"
            report["recommended_action"] = "Confirm RPC node synchronization and chain ID before considering recovery."
            return report
        if not expected:
            report["status"] = "missing_checkpoint_hash"
            report["recommended_action"] = "Inspect the worker's checkpoint migration; do not invent a hash."
            return report

        canonical = await client.get_block(height)
        actual = normalized_hash(canonical.get("hash"))
        report["checks"]["canonical_at_cursor"] = actual
        report["checks"]["lag_blocks"] = tip - height
        if actual != expected:
            report["status"] = "checkpoint_hash_mismatch"
            report["recommended_action"] = (
                "Worker must verify a retained common ancestor and replay forward atomically; "
                "halt if ancestry cannot be proven. Do not force-reset the cursor."
            )
        elif tip - height > 12:
            report["status"] = "canonical_but_behind"
            report["recommended_action"] = "Inspect worker logs, provider rate limits and block processing throughput."
        else:
            report["status"] = "canonical_checkpoint_verified"
            report["recommended_action"] = "Verify worker continues advancing; a single hash check does not prove ingestion continuity."
        return report
    except Exception as exc:
        report["status"] = "diagnostic_failed"
        report["checks"]["error_type"] = type(exc).__name__
        report["recommended_action"] = "Review database access, schema, RPC logs, and diagnostic stack trace."
        return report
    finally:
        await client.close()
        await close_db()


if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["status"] == "canonical_checkpoint_verified" else 1)
