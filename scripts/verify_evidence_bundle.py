"""Verify a saved ChainScope evidence bundle independently of the live service."""
import argparse
import hashlib
import json
from pathlib import Path

FIELDS = ("hash", "from_address", "to_address", "value_wei",
          "block_number", "timestamp", "risk_score", "risk_factors")


def digest_rows(rows):
    normalized = [{field: row.get(field) for field in FIELDS} for row in rows]
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                           default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_bundle(bundle):
    if bundle.get("schema_version") != "chainscope-evidence-bundle-v1":
        raise ValueError("Unsupported evidence bundle format")
    if bundle.get("chain_id") != 1:
        raise ValueError("Unexpected Ethereum chain ID")
    rows = bundle.get("transactions")
    if not isinstance(rows, list):
        raise ValueError("Transactions must be a list")
    claimed = bundle.get("integrity", {}).get("digest")
    actual = digest_rows(rows)
    if actual != claimed:
        raise ValueError("Evidence digest mismatch: exported records were modified")
    coverage = bundle.get("coverage", {})
    if coverage.get("exported_transactions") != len(rows):
        raise ValueError("Coverage count does not match exported records")
    return {"verified": True, "transactions": len(rows),
            "digest": actual, "truncated": coverage.get("truncated")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_bundle(json.loads(args.bundle.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
