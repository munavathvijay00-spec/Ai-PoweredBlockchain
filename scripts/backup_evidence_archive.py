"""Offline backup and restore for an operator-controlled ChainScope evidence archive.

No automatic pruning, remote transfer, or production database modification.
Restore refuses an existing target and verifies every saved bundle before use.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from pathlib import Path

from scripts.evidence_archive import EvidenceArchive, MAX_BUNDLES, MAX_TOTAL_BYTES


def verify_archive(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected a regular archive database")
    with EvidenceArchive(path) as archive:
        integrity = archive.db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("SQLite database integrity check failed")
        rows = archive.db.execute(
            "SELECT digest, size_bytes FROM preserved_bundles ORDER BY digest"
        ).fetchall()
        total = sum(size for _, size in rows)
        if len(rows) > MAX_BUNDLES or total > MAX_TOTAL_BYTES:
            raise ValueError("Archive exceeds supported capacity")
        for digest, size in rows:
            if size < 0:
                raise ValueError("Invalid saved record length")
            archive.retrieve(digest)
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
