"""Dependency-light, non-destructive checkpoint recovery fault drill.

Exercises the production reconciliation function with isolated fake database
and RPC dependencies. Does NOT modify a cursor, contact Ethereum, stop the
Render worker, or measure production restart latency.

Run: python scripts/run_recovery_fault_drill.py
"""

from __future__ import annotations

import asyncio
import ast
import importlib.util
import json
import sys
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOOD_HASH = "0x" + "a" * 64
BAD_HASH = "0x" + "b" * 64


def load_production_reconciler():
    """Load the actual module while stubbing only its two I/O dependencies."""
    original = {name: sys.modules.get(name) for name in (
        "src.ingest.cursor", "src.ingest.reorg",
    )}
    cursor = types.ModuleType("src.ingest.cursor")
    reorg = types.ModuleType("src.ingest.reorg")

    async def load_cursor_checkpoint(db):
        return db.height, db.block_hash

    cursor.load_cursor_checkpoint = load_cursor_checkpoint
    reorg.block_hash = lambda value: str(value).lower()
    try:
        sys.modules["src.ingest.cursor"] = cursor
        sys.modules["src.ingest.reorg"] = reorg
        path = ROOT / "src/ingest/checkpoint_reconcile.py"
        spec = importlib.util.spec_from_file_location("_chainscope_fault_reconciler", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.reconcile_competing_worker
    finally:
        for name, existing in original.items():
            if existing is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = existing


def load_production_retry_policy():
    """Extract the pure helper without importing network/database dependencies."""
    path = ROOT / "src/ingest/loop.py"
    nodes = ast.parse(path.read_text(encoding="utf-8")).body
    function = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == "ingestion_retry_delay")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["ingestion_retry_delay"]


class MemoryCheckpoint:
    def __init__(self, height=106, block_hash=GOOD_HASH):
        self.height, self.block_hash = height, block_hash


class FakeRPC:
    def __init__(self, *, canonical_hash=GOOD_HASH, failures=0, latency=0):
        self.canonical_hash = canonical_hash
        self.failures = failures
        self.latency = latency
        self.calls = 0

    async def get_block(self, height, *, full_transactions):
        self.calls += 1
        if self.latency:
            await asyncio.sleep(self.latency)
        if self.calls <= self.failures:
            raise ConnectionError("simulated RPC timeout")
        return {"number": height, "hash": self.canonical_hash}


async def drill():
    reconcile = load_production_reconciler()
    retry_delay = load_production_retry_policy()
    results = []

    async def run_case(name, operation, expected, **metadata):
        start = time.perf_counter()
        outcome = await operation()
        assert outcome == expected, f"{name}: {outcome!r} != {expected!r}"
        results.append({"scenario": name, "outcome": "pass", "elapsed_ms": round((time.perf_counter() - start) * 1000, 3), **metadata})

    await run_case(
        "newer canonical checkpoint conflict",
        lambda: reconcile(MemoryCheckpoint(), FakeRPC(), 100),
        (106, GOOD_HASH),
    )

    async def noncanonical():
        try:
            await reconcile(MemoryCheckpoint(), FakeRPC(canonical_hash=BAD_HASH), 100)
        except RuntimeError as error:
            return "LINEAGE_CONFLICT" if "LINEAGE_CONFLICT" in str(error) else "unexpected_error"
        return "incorrectly_resumed"

    await run_case("noncanonical checkpoint fails closed", noncanonical, "LINEAGE_CONFLICT")

    async def interrupted_worker():
        client = FakeRPC(latency=0.1)
        task = asyncio.create_task(reconcile(MemoryCheckpoint(), client, 100))
        await asyncio.sleep(0.005)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # A new worker can read the same unchanged persisted checkpoint.
        return await reconcile(MemoryCheckpoint(), FakeRPC(), 100)

    await run_case("worker interruption then safe restart", interrupted_worker, (106, GOOD_HASH))

    async def rpc_failures_then_success():
        client = FakeRPC(failures=2)
        attempts = 0
        while attempts < 3:
            attempts += 1
            try:
                winner = await reconcile(MemoryCheckpoint(), client, 100)
                return {"checkpoint": winner, "attempts": attempts}
            except ConnectionError:
                # Scale actual waits down: this is NOT wall-clock production recovery.
                assert retry_delay(attempts, 15) in (15, 30)
                await asyncio.sleep(0.005)
        raise AssertionError("RPC recovery failed")

    await run_case(
        "two transient RPC failures then recovery",
        rpc_failures_then_success,
        {"checkpoint": (106, GOOD_HASH), "attempts": 3},
        configured_retry_seconds=[15, 30],
    )
    return {
        "environment": "isolated_fake_db_and_rpc",
        "production_restart_time_measured": False,
        "scenarios_passed": len(results),
        "scenarios": results,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(drill()), indent=2))
