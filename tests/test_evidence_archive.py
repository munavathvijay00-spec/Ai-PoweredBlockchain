"""Bounded local evidence archive regression checks."""
import hashlib
import json
import sqlite3
import pytest

from scripts.evidence_archive import EvidenceArchive, MAX_BUNDLE_BYTES
from scripts.verify_evidence_bundle import digest_rows


def bundle():
    rows = [{"hash": "0x" + "a" * 64, "risk_score": 25}]
    result = {
        "schema_version": "chainscope-evidence-bundle-v2", "chain_id": 1,
        "transactions": rows, "coverage": {"exported_transactions": 1},
        "integrity": {"digest": digest_rows(rows), "manifest_algorithm": "sha256"},
    }
    result["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in result.items() if k != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    return result


def test_archive_survives_reopen_and_is_idempotent(tmp_path):
    db = tmp_path / "archive.db"
    with EvidenceArchive(db) as archive:
        digest = archive.preserve(bundle())
        assert archive.preserve(bundle()) == digest
        assert archive.retrieve(digest) == bundle()
    with EvidenceArchive(db) as archive:
        assert archive.retrieve(digest) == bundle()


def test_archive_detects_stored_tampering(tmp_path):
    db = tmp_path / "archive.db"
    with EvidenceArchive(db) as archive:
        digest = archive.preserve(bundle())
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE preserved_bundles SET payload = ? WHERE digest = ?",
            (b'{"changed":true}', digest),
        )
    with EvidenceArchive(db) as archive:
        with pytest.raises(ValueError, match="checksum"):
            archive.retrieve(digest)


def test_archive_rejects_invalid_evidence(tmp_path):
    with EvidenceArchive(tmp_path / "archive.db") as archive:
        invalid = bundle()
        invalid["transactions"][0]["risk_score"] = 100
        with pytest.raises(ValueError):
            archive.preserve(invalid)
        with pytest.raises(ValueError, match="identifier"):
            archive.retrieve("../../etc/passwd")
