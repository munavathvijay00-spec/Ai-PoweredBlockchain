"""Persistent registry for independently supervised ML models.

Railway containers are ephemeral, so production model artifacts and provenance are
stored in PostgreSQL. Only independently supervised, feature-compatible model bundles
may be registered or used for shadow inference.
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional

import joblib
import numpy as np

from src.database.connection import get_db
from src.ml.independent_model import (
    FEATURE_COLUMNS,
    MODEL_FAMILY,
    _vector,
    load_independent_bundle,
    train_independent_model,
)

MODEL_NAME = "independent_transaction_risk"


async def ensure_model_registry_schema(db=None) -> None:
    db = db or await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ml_model_registry (
            id BIGSERIAL PRIMARY KEY,
            model_name TEXT NOT NULL,
            version TEXT NOT NULL,
            supervision TEXT NOT NULL,
            deployment_mode TEXT NOT NULL,
            quality_gate_passed BOOLEAN NOT NULL DEFAULT FALSE,
            artifact BYTEA NOT NULL,
            metadata JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(model_name, version)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_ml_model_registry_active
        ON ml_model_registry(model_name, created_at DESC)
    """)


def _serialize(bundle: Dict[str, Any]) -> bytes:
    stream = io.BytesIO()
    joblib.dump(bundle, stream)
    return stream.getvalue()


def _validate_metadata(metadata: Dict[str, Any]) -> None:
    if metadata.get("supervision") != "independent_external_labels":
        raise ValueError("Model provenance gate failed")
    if tuple(metadata.get("features") or ()) != FEATURE_COLUMNS:
        raise ValueError("Model feature schema mismatch")
    if metadata.get("model_family") != MODEL_FAMILY:
        raise ValueError(
            f"Model runtime family mismatch: expected {MODEL_FAMILY}, got {metadata.get('model_family') or 'legacy'}"
        )


def _deserialize(blob: bytes) -> Dict[str, Any]:
    bundle = joblib.load(io.BytesIO(bytes(blob)))
    if not isinstance(bundle, dict):
        raise ValueError("Invalid model bundle")
    metadata = bundle.get("metadata") or {}
    _validate_metadata(metadata)
    return bundle


async def train_and_register(limit: int = 5000) -> Dict[str, Any]:
    """Train from external labels and persist artifact + immutable provenance."""
    db = await get_db()
    await ensure_model_registry_schema(db)
    metadata = await train_independent_model(limit=limit)
    _validate_metadata(metadata)
    bundle = load_independent_bundle()
    artifact = _serialize(bundle)
    version = f"{metadata['trained_at']}:{metadata['dataset_fingerprint_sha256'][:12]}:{MODEL_FAMILY}"
    await db.execute("""
        INSERT INTO ml_model_registry
          (model_name, version, supervision, deployment_mode,
           quality_gate_passed, artifact, metadata)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
        ON CONFLICT (model_name, version) DO NOTHING
    """,
        MODEL_NAME,
        version,
        metadata["supervision"],
        metadata["deployment_mode"],
        bool(metadata["production_quality_gate_passed"]),
        artifact,
        json.dumps(metadata),
    )
    return {**metadata, "model_name": MODEL_NAME, "version": version, "registered": True}


async def latest_model_record() -> Optional[Dict[str, Any]]:
    db = await get_db()
    await ensure_model_registry_schema(db)
    row = await db.fetchrow("""
        SELECT model_name, version, supervision, deployment_mode,
               quality_gate_passed, metadata, created_at
        FROM ml_model_registry
        WHERE model_name=$1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """, MODEL_NAME)
    return dict(row) if row else None


async def model_status() -> Dict[str, Any]:
    row = await latest_model_record()
    if not row:
        return {
            "available": False,
            "model_name": MODEL_NAME,
            "deployment_mode": "not_trained",
            "model_family": MODEL_FAMILY,
            "runtime_compatible": False,
            "production_quality_gate_passed": False,
        }
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    family = metadata.get("model_family")
    runtime_compatible = bool(
        family == MODEL_FAMILY
        and metadata.get("supervision") == "independent_external_labels"
        and tuple(metadata.get("features") or ()) == FEATURE_COLUMNS
    )
    return {
        "available": True,
        "model_name": row["model_name"],
        "version": row["version"],
        "model_family": family or "legacy_unknown",
        "expected_model_family": MODEL_FAMILY,
        "runtime_compatible": runtime_compatible,
        "supervision": row["supervision"],
        "deployment_mode": row["deployment_mode"] if runtime_compatible else "migration_required",
        "production_quality_gate_passed": bool(row["quality_gate_passed"] and runtime_compatible),
        "dataset_rows": metadata.get("dataset_rows"),
        "sample_tier": metadata.get("sample_tier"),
        "test_metrics": metadata.get("test_metrics"),
        "validation_metrics": metadata.get("validation_metrics"),
        "threshold": metadata.get("threshold"),
        "trained_at": metadata.get("trained_at"),
        "dataset_fingerprint_sha256": metadata.get("dataset_fingerprint_sha256"),
        "limitations": metadata.get("limitations") or [],
    }


async def _load_latest_bundle() -> tuple[Dict[str, Any], Dict[str, Any]]:
    db = await get_db()
    await ensure_model_registry_schema(db)
    row = await db.fetchrow("""
        SELECT artifact, metadata, version, deployment_mode, quality_gate_passed
        FROM ml_model_registry
        WHERE model_name=$1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """, MODEL_NAME)
    if not row:
        raise FileNotFoundError("No independently supervised model is registered")

    metadata = row["metadata"] or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    # Check compatibility before unpickling, so a legacy artifact cannot force imports
    # for a model library that is intentionally absent from the production image.
    _validate_metadata(metadata)
    return _deserialize(row["artifact"]), dict(row)


async def predict_shadow(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return calibrated ML signal without mutating ChainScope's production risk score."""
    bundle, registry = await _load_latest_bundle()
    model = bundle["model"]
    calibrator = bundle["calibrator"]
    metadata = bundle["metadata"]
    raw = float(model.predict_proba(np.asarray([_vector(row)], dtype=float))[0, 1])
    probability = float(calibrator.predict_proba(np.asarray([[raw]], dtype=float))[0, 1])
    threshold = float(metadata["threshold"])
    return {
        "model_name": MODEL_NAME,
        "version": registry["version"],
        "model_family": metadata.get("model_family"),
        "label": int(probability >= threshold),
        "calibrated_score": probability,
        "threshold": threshold,
        "deployment_mode": registry["deployment_mode"],
        "production_quality_gate_passed": bool(registry["quality_gate_passed"]),
        "interpretation": "Independent ML review signal; not a probability of criminality and not part of the production risk score.",
    }
