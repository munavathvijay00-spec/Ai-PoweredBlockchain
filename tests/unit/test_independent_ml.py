from src.ml.independent_model import FEATURE_COLUMNS, _bucket, build_features


def test_feature_schema_excludes_detector_outputs_and_labels():
    forbidden = {
        "risk_score", "risk_factors", "label", "to_blacklisted", "from_blacklisted",
        "entity_match", "detector_score", "ai_explanation",
    }
    assert forbidden.isdisjoint(set(FEATURE_COLUMNS))


def test_build_features_ignores_chain_scope_risk_fields():
    base = {
        "value": 10**18,
        "gas_used": 21000,
        "gas_price": 20 * 10**9,
        "timestamp": "2026-10-14T12:00:00+00:00",
    }
    poisoned = {
        **base,
        "risk_score": 100,
        "risk_factors": [{"factor": "blacklisted_address", "points": 100}],
        "label": 1,
        "to_blacklisted": 1,
        "from_blacklisted": 1,
    }
    assert build_features(base) == build_features(poisoned)


def test_hash_bucket_is_stable_and_uses_all_partitions():
    tx_hash = "0x" + "ab" * 32
    first = _bucket(tx_hash)
    assert first in {"train", "validation", "test"}
    assert _bucket(tx_hash) == first

    hashes = ["0x" + f"{i:064x}" for i in range(200)]
    partitions = {_bucket(h) for h in hashes}
    assert partitions == {"train", "validation", "test"}


def test_external_feature_builder_supports_live_and_dataset_shapes():
    external = {
        "value_wei_text": str(2 * 10**18),
        "gas": 42000,
        "gas_price_text": str(30 * 10**9),
        "block_timestamp_text": "2026-10-14T09:30:00+00:00",
    }
    live = {
        "value": 2 * 10**18,
        "gas_used": 42000,
        "gas_price": 30 * 10**9,
        "timestamp": "2026-10-14T09:30:00+00:00",
    }
    assert build_features(external) == build_features(live)
