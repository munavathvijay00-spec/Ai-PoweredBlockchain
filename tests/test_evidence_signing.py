from types import SimpleNamespace

from src.forensics import evidence_signing


def test_unsigned_status_when_key_not_configured(monkeypatch):
    monkeypatch.setattr(
        evidence_signing,
        "get_settings",
        lambda: SimpleNamespace(evidence_signing_key="", evidence_signer_id="test-signer"),
    )
    result = evidence_signing.sign_digest_hex("00" * 32)
    assert result["status"] == "unsigned"
    assert result["signature"] is None
    assert result["public_key"] is None


def test_ed25519_signature_is_deterministic_for_digest(monkeypatch):
    seed_hex = bytes(range(32)).hex()
    monkeypatch.setattr(
        evidence_signing,
        "get_settings",
        lambda: SimpleNamespace(evidence_signing_key=seed_hex, evidence_signer_id="test-signer"),
    )
    digest = "ab" * 32
    first = evidence_signing.sign_digest_hex(digest)
    second = evidence_signing.sign_digest_hex(digest)
    assert first["status"] == "signed"
    assert first["algorithm"] == "Ed25519-over-SHA256"
    assert first["signer_id"] == "test-signer"
    assert first["signature"] == second["signature"]
    assert first["public_key"] == second["public_key"]


def test_invalid_signing_key_fails_closed(monkeypatch):
    monkeypatch.setattr(
        evidence_signing,
        "get_settings",
        lambda: SimpleNamespace(evidence_signing_key="not-a-valid-seed", evidence_signer_id="test-signer"),
    )
    result = evidence_signing.sign_digest_hex("12" * 32)
    assert result["status"] == "unsigned_error"
    assert result["signature"] is None
