"""End-to-end CLI check: preserve → sign → verify, with an isolated temporary key."""
import hashlib
import json
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.verify_evidence_bundle import digest_rows


def test_offline_evidence_cli_round_trip(tmp_path):
    rows = [{"hash": "0x" + "a" * 64, "value_wei": "42", "risk_score": 25}]
    payload = {
        "schema_version": "chainscope-evidence-bundle-v2",
        "chain_id": 1,
        "transactions": rows,
        "coverage": {"exported_transactions": 1, "truncated": False},
        "integrity": {
            "algorithm": "sha256", "digest": digest_rows(rows),
            "manifest_algorithm": "sha256",
        },
    }
    payload["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in payload.items() if k != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()

    unsigned_path = tmp_path / "evidence.json"
    signed_path = tmp_path / "signed.json"
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "trusted-public.pem"
    unsigned_path.write_text(json.dumps(payload), encoding="utf-8")
    key = Ed25519PrivateKey.generate()
    private_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))

    sign = subprocess.run([
        sys.executable, "-m", "scripts.sign_evidence_bundle", "sign",
        str(unsigned_path), "--private-key", str(private_path),
        "--output", str(signed_path),
    ], capture_output=True, text=True)
    assert sign.returncode == 0, sign.stderr

    verify = subprocess.run([
        sys.executable, "-m", "scripts.sign_evidence_bundle", "verify",
        str(signed_path), "--public-key", str(public_path),
    ], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["authenticated"] is True

    altered = json.loads(signed_path.read_text(encoding="utf-8"))
    altered["coverage"]["truncated"] = True
    signed_path.write_text(json.dumps(altered), encoding="utf-8")
    reject = subprocess.run([
        sys.executable, "-m", "scripts.sign_evidence_bundle", "verify",
        str(signed_path), "--public-key", str(public_path),
    ], capture_output=True, text=True)
    assert reject.returncode != 0
