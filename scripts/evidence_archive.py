"""Local, bounded evidence archive for operator-preserved ChainScope bundles.

This is NOT a public web API or automatic server archive. Operators must
provision a persistent, access-controlled path and arrange backups separately.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.verify_evidence_bundle import verify_bundle

MAX_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_BUNDLES = 100
MAX_TOTAL_BYTES = 100 * 1024 * 1024


def canonical_bytes(bundle: dict) -> bytes:
    return json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class EvidenceArchive:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("Archive database must not be a symlink")
        self.db = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS preserved_bundles (
                digest TEXT PRIMARY KEY, saved_at TEXT NOT NULL,
                payload BLOB NOT NULL, size_bytes INTEGER NOT NULL
            )
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def preserve(self, bundle: dict) -> str:
        verify_bundle(bundle)
        content = canonical_bytes(bundle)
        size = len(content)
        if size > MAX_BUNDLE_BYTES:
            raise ValueError("Evidence bundle exceeds archive record limit")
        digest = hashlib.sha256(content).hexdigest()
        # BEGIN IMMEDIATE serializes capacity checks and concurrent writers.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT 1 FROM preserved_bundles WHERE digest = ?", (digest,)
            ).fetchone()
            if not existing:
                count, total = self.db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM preserved_bundles"
                ).fetchone()
                if count >= MAX_BUNDLES or total + size > MAX_TOTAL_BYTES:
                    raise ValueError("Archive capacity reached; no evidence was evicted")
                self.db.execute(
                    "INSERT INTO preserved_bundles(digest, saved_at, payload, size_bytes) VALUES (?, ?, ?, ?)",
                    (digest, datetime.now(timezone.utc).isoformat(), content, size),
                )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return digest

    def retrieve(self, digest: str) -> dict:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid archive identifier")
        row = self.db.execute(
            "SELECT payload FROM preserved_bundles WHERE digest = ?", (digest,)
        ).fetchone()
        if row is None:
            raise KeyError("Bundle not found")
        raw = bytes(row[0])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Stored evidence checksum mismatch")
        result = json.loads(raw)
        verify_bundle(result)
        return result
