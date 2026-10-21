"""Offline backup and restore for an operator-controlled ChainScope evidence archive.

No automatic pruning, remote transfer, or production database modification.
Restore refuses an existing target and verifies every saved bundle before use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from scripts.evidence_archive import MAX_BUNDLES, MAX_TOTAL_BYTES
from scripts.verify_evidence_bundle import verify_bundle


def verify_archive(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected a regular archive database")
    # Verify without creating tables, writing WAL or changing source permissions.
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("SQLite database integrity check failed")
        schema = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='preserved_bundles'"
        ).fetchone()
        if schema is None:
            raise ValueError("Not a ChainScope evidence archive: table missing")
        rows = db.execute(
            "SELECT digest, payload, size_bytes FROM preserved_bundles ORDER BY digest"
        ).fetchall()
        total = 0
        if len(rows) > MAX_BUNDLES:
            raise ValueError("Archive exceeds supported capacity")
        for digest, payload, declared_size in rows:
            raw = bytes(payload)
            if declared_size != len(raw):
                raise ValueError("Archive record size mismatch")
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("Stored evidence checksum mismatch")
            verify_bundle(json.loads(raw))
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Archive exceeds supported capacity")
        return {"bundles_verified": len(rows), "payload_bytes": total}

def backup_archive(source: Path, destination: Path) -> dict:
    if not source.is_file() or source.is_symlink():
        raise ValueError("Source archive does not exist or is unsafe")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Backup destination already exists")
    if not destination.parent.is_dir():
        raise ValueError("Backup directory must already exist")
    verify_archive(source)
    # Exclusive create prevents replacing an existing artifact.
    fd = os.open(destination, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source) as live, sqlite3.connect(destination) as saved:
            live.backup(saved)
        return verify_archive(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def restore_archive(source: Path, destination: Path) -> dict:
    # Restore is deliberately a verified copy to a new path only.
    return backup_archive(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_archive(args.source)
    else:
        if args.destination is None:
            parser.error("backup and restore require a destination path")
        result = backup_archive(args.source, args.destination)
    print(result)


if __name__ == "__main__":
    main()
