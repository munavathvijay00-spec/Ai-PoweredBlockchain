"""Join blind human labels with sealed detector predictions and evaluate them.

The files stay separate until evaluation time to prevent label leakage. When a
manifest is supplied, ChainScope verifies the sealed prediction hash before any
metric is produced.

Usage:
    python scripts/evaluate_blind_holdout.py labels.csv predictions.csv [manifest.json]
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

from scripts.evaluate_detection import evaluate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_unique(path: str, required: set[str]) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = required.difference(reader.fieldnames or [])
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                raise ValueError(f"Blank case_id in {path}")
            if case_id in rows:
                raise ValueError(f"Duplicate case_id {case_id} in {path}")
            rows[case_id] = row
        return rows


def _verify_manifest(manifest_path: str, predictions_path: str) -> dict:
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("labeling_protocol") != "blind_independent_adjudication":
        raise ValueError("Manifest does not declare blind independent adjudication")
    leakage = manifest.get("leakage_control") or {}
    if leakage.get("labels_file_contains_predictions") is not False:
        raise ValueError("Manifest does not prove labels are prediction-free")
    if leakage.get("cases_file_contains_detector_signals") is not False:
        raise ValueError("Manifest does not prove cases are detector-signal-free")
    expected = (manifest.get("files") or {}).get("predictions.csv")
    if not expected:
        raise ValueError("Manifest is missing the sealed predictions.csv SHA-256")
    actual = _sha256_file(Path(predictions_path))
    if actual != expected:
        raise ValueError("Sealed predictions hash mismatch; evaluation aborted")
    return manifest


def join_rows(labels_path: str, predictions_path: str) -> list[dict[str, str]]:
    labels = _read_unique(
        labels_path,
        {
            "case_id",
            "actual_label",
            "label_source",
            "label_evidence_url",
            "adjudicator_id",
            "adjudicated_at",
        },
    )
    predictions = _read_unique(predictions_path, {"case_id", "predicted_flag"})

    if set(labels) != set(predictions):
        only_labels = sorted(set(labels).difference(predictions))[:10]
        only_predictions = sorted(set(predictions).difference(labels))[:10]
        raise ValueError(
            "Label/prediction case mismatch; "
            f"labels_only={only_labels}, predictions_only={only_predictions}"
        )

    joined = []
    for case_id in sorted(labels):
        row = labels[case_id]
        label = str(row.get("actual_label") or "").strip()
        if label not in {"0", "1"}:
            raise ValueError(f"Case {case_id} is not independently adjudicated with 0 or 1")
        if not str(row.get("label_source") or "").strip():
            raise ValueError(f"Case {case_id} is missing independent label_source")
        if not str(row.get("label_evidence_url") or "").strip():
            raise ValueError(f"Case {case_id} is missing label_evidence_url")
        if not str(row.get("adjudicator_id") or "").strip():
            raise ValueError(f"Case {case_id} is missing adjudicator_id")
        if not str(row.get("adjudicated_at") or "").strip():
            raise ValueError(f"Case {case_id} is missing adjudicated_at")
        joined.append({
            "case_id": case_id,
            "actual_label": label,
            "predicted_flag": str(predictions[case_id].get("predicted_flag") or "").strip(),
        })
    return joined


def main(labels_path: str, predictions_path: str, manifest_path: str | None = None) -> None:
    manifest = _verify_manifest(manifest_path, predictions_path) if manifest_path else None
    joined = join_rows(labels_path, predictions_path)
    if not joined:
        raise ValueError("No cases supplied")
    result = evaluate(joined)
    result["evaluation_protocol"] = {
        "name": "blind_independent_holdout",
        "labels_path": labels_path,
        "predictions_path": predictions_path,
        "manifest_path": manifest_path,
        "dataset_id": manifest.get("dataset_id") if manifest else None,
        "sealed_predictions_verified": bool(manifest),
        "labeler_prediction_visibility_required": False,
        "label_provenance_required": True,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(
            "Usage: python scripts/evaluate_blind_holdout.py labels.csv predictions.csv [manifest.json]"
        )
    try:
        main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
