"""Offline Ed25519 authentication for preserved ChainScope evidence bundles.

No signing key is stored in the repository or accessed by the web API.
This tool signs the canonical bundle payload, including the recorded integrity
digests. Verification requires a separately trusted public key.
"""
import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from scripts.verify_evidence_bundle import verify_bundle


def signed_bytes(bundle):
    return json.dumps({k: v for k, v in bundle.items() if k != "signature"},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_bundle(bundle, private_key):
    verify_bundle(bundle)
    if "signature" in bundle:
        raise ValueError("Bundle already signed")
    signature = base64.b64encode(private_key.sign(signed_bytes(bundle))).decode("ascii")
    return {**bundle, "signature": {"algorithm": "Ed25519", "encoding": "base64",
                                   "value": signature}}


def verify_signed_bundle(bundle, trusted_public_key):
    verify_bundle(bundle)
    signature = bundle.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "Ed25519" or signature.get("encoding") != "base64":
        raise ValueError("Missing or unsupported authenticated signature")
    try:
        value = base64.b64decode(signature["value"], validate=True)
        trusted_public_key.verify(value, signed_bytes(bundle))
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Signature verification failed") from exc
    except Exception as exc:
        raise ValueError("Signature verification failed") from exc
    return {"authenticated": True, "transactions": len(bundle["transactions"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    signing = sub.add_parser("sign")
    signing.add_argument("bundle", type=Path)
    signing.add_argument("--private-key", type=Path, required=True)
    signing.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    if args.command == "sign":
        private = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise ValueError("Expected an Ed25519 private key")
        signed = sign_bundle(bundle, private)
        args.output.write_text(json.dumps(signed, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        public = serialization.load_pem_public_key(args.public_key.read_bytes())
        if not isinstance(public, Ed25519PublicKey):
            raise ValueError("Expected an Ed25519 public key")
        print(json.dumps(verify_signed_bundle(bundle, public), indent=2))


if __name__ == "__main__":
    main()
