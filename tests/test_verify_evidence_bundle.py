"""Independent verification of an exported ChainScope evidence bundle."""
import hashlib
import json
import pytest
from scripts.verify_evidence_bundle import digest_rows, verify_bundle


def fixture_bundle():
    rows = [{"hash": "0x" + "a" * 64, "risk_score": 40, "value_wei": "100"}]
    bundle = {
        "schema_version": "chainscope-evidence-bundle-v2",
        "chain_id": 1,
        "transactions": rows,
        "integrity": {"digest": digest_rows(rows), "manifest_algorithm": "sha256"},
        "coverage": {"exported_transactions": 1, "truncated": False},
    }
    bundle["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {key: value for key, value in bundle.items() if key != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return bundle


def test_valid_bundle():
    result = verify_bundle(fixture_bundle())
    assert result["verified"] is True
    assert result["transactions"] == 1


def test_modified_transaction_is_rejected():
    bundle = fixture_bundle()
    bundle["transactions"][0]["risk_score"] = 99
    with pytest.raises(ValueError, match="digest"):
        verify_bundle(bundle)


def test_count_mismatch_is_rejected():
    bundle = fixture_bundle()
    bundle["coverage"]["exported_transactions"] = 2
    bundle["integrity"]["manifest_digest"] = hashlib.sha256(json.dumps(
        {key: value for key, value in bundle.items() if key != "integrity"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="count"):
        verify_bundle(bundle)


def test_metadata_tampering_is_rejected():
    bundle = fixture_bundle()
    bundle["coverage"]["truncated"] = True
    with pytest.raises(ValueError, match="manifest"):
        verify_bundle(bundle)
