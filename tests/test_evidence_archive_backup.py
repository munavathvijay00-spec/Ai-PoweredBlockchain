"""Verify SQLite backup and restore of preserved evidence."""
import hashlib
import json
import sqlite3
import pytest
from scripts.evidence_archive import EvidenceArchive
from scripts.backup_evidence_archive import backup_archive, restore_archive, verify_archive
from scripts.verify_evidence_bundle import digest_rows


def bundle():
    rows = [{"hash": "0x" + "a" * 64, "risk_score": 25}]
    data = {"schema_version": "chainscope-evidence-bundle-v2", "chain_id": 1,
            "transactions": rows, "coverage": {"exported_transactions": 1},
            "integrity": {"digest": digest_rows(rows), "manifest_algorithm": "sha256"}}
    data["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in data.items() if k != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    return data


def test_backup_and_restore_survive_reopen(tmp_path):
    source, backup, restored = (tmp_path / x for x in ("source.db", "backup.db", "restored.db"))
    with EvidenceArchive(source) as archive:
        identifier = archive.preserve(bundle())
        assert backup_archive(source, backup)["bundles_verified"] == 1
    assert restore_archive(backup, restored)["bundles_verified"] == 1
    with EvidenceArchive(restored) as archive:
        assert archive.retrieve(identifier) == bundle()


def test_backup_never_overwrites(tmp_path):
    source, backup = tmp_path / "source.db", tmp_path / "backup.db"
    with EvidenceArchive(source) as archive:
        archive.preserve(bundle())
    backup_archive(source, backup)
    with pytest.raises(FileExistsError):
        backup_archive(source, backup)


def test_corrupted_archive_fails_verification(tmp_path):
    source = tmp_path / "bad.db"
    source.write_bytes(b"not a sqlite archive")
    with pytest.raises(Exception):
        verify_archive(source)


def test_missing_archive_schema_is_rejected_without_mutation(tmp_path):
    path = tmp_path / "empty.db"
    with sqlite3.connect(path):
        pass
    original = path.read_bytes()
    with pytest.raises(ValueError, match="table missing"):
        verify_archive(path)
    assert path.read_bytes() == original


def test_record_size_mismatch_is_rejected(tmp_path):
    path = tmp_path / "archive.db"
    with EvidenceArchive(path) as archive:
        identifier = archive.preserve(bundle())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE preserved_bundles SET size_bytes = size_bytes + 1 WHERE digest = ?", (identifier,))
    with pytest.raises(ValueError, match="size mismatch"):
        verify_archive(path)


def test_failed_backup_never_publishes_partial_destination(tmp_path, monkeypatch):
    import scripts.backup_evidence_archive as module
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with EvidenceArchive(source) as archive:
        archive.preserve(bundle())
    original = module.verify_archive
    def reject_stage(path):
        if path != source:
            raise ValueError("Injected verification failure")
        return original(path)
    monkeypatch.setattr(module, "verify_archive", reject_stage)
    with pytest.raises(ValueError, match="Injected"):
        module.backup_archive(source, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".chainscope-backup-*"))


def test_backup_destination_race_cannot_overwrite(tmp_path, monkeypatch):
    import scripts.backup_evidence_archive as module
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with EvidenceArchive(source) as archive:
        archive.preserve(bundle())
    original = module.verify_archive
    def occupy_destination(path):
        result = original(path)
        if path != source:
            destination.write_text("existing data")
        return result
    monkeypatch.setattr(module, "verify_archive", occupy_destination)
    with pytest.raises(FileExistsError):
        module.backup_archive(source, destination)
    assert destination.read_text() == "existing data"
    assert not list(tmp_path.glob(".chainscope-backup-*"))
