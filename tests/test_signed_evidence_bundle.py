"""Offline evidence-signature tests; no real keys or external services."""
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts.sign_evidence_bundle import sign_bundle, verify_signed_bundle
from scripts.verify_evidence_bundle import digest_rows
import json, hashlib


def bundle():
    rows = [{"hash": "0x" + "a" * 64, "risk_score": 25}]
    data = {"schema_version": "chainscope-evidence-bundle-v2", "chain_id": 1,
            "transactions": rows, "coverage": {"exported_transactions": 1},
            "integrity": {"algorithm": "sha256", "digest": digest_rows(rows),
                          "manifest_algorithm": "sha256"}}
    data["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in data.items() if k != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    return data


def test_signature_round_trip():
    key = Ed25519PrivateKey.generate()
    signed = sign_bundle(bundle(), key)
    assert verify_signed_bundle(signed, key.public_key())["authenticated"]
    with pytest.raises(ValueError):
        sign_bundle(signed, key)


def test_modified_bundle_is_rejected():
    key = Ed25519PrivateKey.generate()
    signed = sign_bundle(bundle(), key)
    signed["transactions"][0]["risk_score"] = 99
    with pytest.raises(ValueError):
        verify_signed_bundle(signed, key.public_key())


def test_untrusted_public_key_is_rejected():
    key = Ed25519PrivateKey.generate()
    signed = sign_bundle(bundle(), key)
    with pytest.raises(ValueError, match="Signature"):
        verify_signed_bundle(signed, Ed25519PrivateKey.generate().public_key())
