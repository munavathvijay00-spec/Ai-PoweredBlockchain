"""Cryptographic signing helpers for exported investigation evidence.

Signatures are optional and fail closed to an explicit unsigned status when a private
key is not configured. The key is never returned; only the public verification key is.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.utils.config import get_settings


def _decode_private_key(value: str) -> bytes:
    raw = value.strip()
    if not raw:
        raise ValueError("empty signing key")
    # Accept a 32-byte seed encoded as hex or url-safe/base64 for deployment ease.
    try:
        decoded = bytes.fromhex(raw)
        if len(decoded) == 32:
            return decoded
    except ValueError:
        pass
    try:
        padding = "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(raw + padding)
        if len(decoded) == 32:
            return decoded
    except (ValueError, binascii.Error):
        pass
    raise ValueError("EVIDENCE_SIGNING_KEY must encode exactly 32 bytes")


def sign_digest_hex(digest_hex: str) -> dict[str, Any]:
    settings = get_settings()
    configured = (settings.evidence_signing_key or "").strip()
    if not configured:
        return {
            "status": "unsigned",
            "algorithm": None,
            "signer_id": None,
            "public_key": None,
            "signature": None,
            "reason": "EVIDENCE_SIGNING_KEY is not configured",
        }
    try:
        digest = bytes.fromhex(digest_hex)
        if len(digest) != 32:
            raise ValueError("digest must be SHA-256")
        private_key = Ed25519PrivateKey.from_private_bytes(_decode_private_key(configured))
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signature = private_key.sign(digest)
        return {
            "status": "signed",
            "algorithm": "Ed25519-over-SHA256",
            "signer_id": settings.evidence_signer_id,
            "public_key": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
            "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
            "reason": None,
        }
    except Exception as exc:
        return {
            "status": "unsigned_error",
            "algorithm": None,
            "signer_id": settings.evidence_signer_id,
            "public_key": None,
            "signature": None,
            "reason": type(exc).__name__,
        }
