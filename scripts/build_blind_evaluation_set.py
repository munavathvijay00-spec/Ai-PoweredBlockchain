"""Build a leakage-resistant evaluation package for ChainScope.

This script deliberately separates what a human labeler sees from what the detector
predicted.  A reviewer must never receive detector outputs while assigning ground
truth.

Usage:
    python scripts/build_blind_evaluation_set.py evidence.json out_dir

Outputs:
    cases.csv        factual case material visible to labelers
    labels.csv       blank adjudication sheet; no model/detector output
    predictions.csv  frozen ChainScope predictions; keep hidden from labelers
    manifest.json    dataset identity and SHA-256 hashes for reproducibility
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CASE_FIELDS = [
    "case_id",
    "tx_hash",
    "from_address",
    "to_address",
    "category",
    "asset",
    "value",
    "token_id",
]
LABEL_FIELDS = [
    "case_id",
    "actual_label",
    "label_source",
    "label_evidence_url",
    "label_notes",
    "adjudicator_id",
    "adjudicated_at",
]
PREDICTION_FIELDS = ["case_id", "predicted_flag", "detector_signals"]


def _canonical(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _identity(transfer: dict[str, Any]) -> str:
    parts = [
        _canonical(transfer.get("hash")).lower(),
        _canonical(transfer.get("from_address")).lower(),
        _canonical(transfer.get("to_address")).lower(),
        _canonical(transfer.get("category")).lower(),
        _canonical(transfer.get("asset")).lower(),
        _canonical(transfer.get("token_id")),
        _canonical(transfer.get("value")),
    ]
    return "|".join(parts)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_package(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(bundle, dict):
        raise ValueError("Evidence bundle must be a JSON object")
    transfers = bundle.get("transfers")
    if not isinstance(transfers, list):
        raise ValueError("Evidence bundle must contain a transfers array")

    report = bundle.get("investigation_report") or {}
    signal_map: dict[str, set[str]] = {}
    for signal in report.get("behavioral_signals") or []:
        if not isinstance(signal, dict):
            continue
        code = _canonical(signal.get("code")) or "review_signal"
        for evidence in signal.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            tx_hash = _canonical(evidence.get("tx_hash"))
            if tx_hash:
                signal_map.setdefault(tx_hash.lower(), set()).add(code)

    cases: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for transfer in transfers:
        if not isinstance(transfer, dict):
            continue
        identity = _identity(transfer)
        if identity in seen:
            continue
        seen.add(identity)
        case_id = "cs-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        tx_hash = _canonical(transfer.get("hash"))
        signals = sorted(signal_map.get(tx_hash.lower(), set()))

        case = {
            "case_id": case_id,
            "tx_hash": tx_hash,
            "from_address": _canonical(transfer.get("from_address")),
            "to_address": _canonical(transfer.get("to_address")),
            "category": _canonical(transfer.get("category")),
            "asset": _canonical(transfer.get("asset")),
            "value": _canonical(transfer.get("value")),
            "token_id": _canonical(transfer.get("token_id")),
        }
        cases.append(case)
        labels.append({
            "case_id": case_id,
            "actual_label": "",
            "label_source": "",
            "label_evidence_url": "",
            "label_notes": "",
            "adjudicator_id": "",
            "adjudicated_at": "",
        })
        predictions.append({
            "case_id": case_id,
            "predicted_flag": "1" if signals else "0",
            "detector_signals": ";".join(signals),
        })

    return cases, labels, predictions


def main(input_path: str, output_dir: str) -> None:
    source = Path(input_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    bundle = json.loads(source.read_text(encoding="utf-8"))
    cases, labels, predictions = build_package(bundle)
    if not cases:
        raise ValueError("No transfer cases found in evidence bundle")

    cases_path = out / "cases.csv"
    labels_path = out / "labels.csv"
    predictions_path = out / "predictions.csv"
    _write_csv(cases_path, CASE_FIELDS, cases)
    _write_csv(labels_path, LABEL_FIELDS, labels)
    _write_csv(predictions_path, PREDICTION_FIELDS, predictions)

    dataset_seed = "\n".join(sorted(row["case_id"] for row in cases))
    dataset_id = "cs-eval-" + hashlib.sha256(dataset_seed.encode("utf-8")).hexdigest()[:16]
    manifest = {
        "dataset_id": dataset_id,
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "labeling_protocol": "blind_independent_adjudication",
        "leakage_control": {
            "labels_file_contains_predictions": False,
            "cases_file_contains_detector_signals": False,
            "predictions_must_be_hidden_from_labelers": True,
        },
        "files": {
            "cases.csv": _sha256_file(cases_path),
            "labels.csv": _sha256_file(labels_path),
            "predictions.csv": _sha256_file(predictions_path),
        },
        "source_bundle_sha256": _sha256_file(source),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Built blind evaluation package {dataset_id} with {len(cases)} cases in {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/build_blind_evaluation_set.py evidence.json out_dir")
    try:
        main(sys.argv[1], sys.argv[2])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
