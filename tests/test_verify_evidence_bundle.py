"""Independent verification of an exported ChainScope evidence bundle."""
import pytest
from scripts.verify_evidence_bundle import digest_rows, verify_bundle


def fixture_bundle():
    rows = [{"hash": "0x" + "a" * 64, "risk_score": 40, "value_wei": "100"}]
    return {
        "schema_version": "chainscope-evidence-bundle-v1",
        "chain_id": 1,
        "transactions": rows,
        "integrity": {"digest": digest_rows(rows)},
        "coverage": {"exported_transactions": 1, "truncated": False},
    }


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
    with pytest.raises(ValueError, match="count"):
        verify_bundle(bundle)
