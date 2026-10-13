"""Create a manual labeling queue from a ChainScope evidence bundle.

This script never creates ground-truth labels. It only freezes the detector
output and evidence references so a separate reviewer can adjudicate cases.

Usage:
    python scripts/build_labeling_queue.py evidence.json labeling_queue.csv

The resulting CSV leaves actual_label, label_source, label_evidence_url and
label_notes blank on purpose. Fill those fields using evidence independent of
ChainScope before running scripts/evaluate_detection.py.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path


FIELDS = [
    "case_id",
    "tx_hash",
    "from_address",
    "to_address",
    "category",
    "asset",
    "value",
    "token_id",
    "predicted_flag",
    "detector_signals",
    "actual_label",
    "label_source",
    "label_evidence_url",
    "label_notes",
]


def _identity(transfer):
    parts = [
        str(transfer.get("hash") or ""),
        str(transfer.get("from_address") or "").lower(),
        str(transfer.get("to_address") or "").lower(),
        str(transfer.get("category") or ""),
        str(transfer.get("asset") or ""),
        str(transfer.get("token_id") or ""),
        str(transfer.get("value") if transfer.get("value") is not None else ""),
    ]
    return "|".join(parts)


def build_rows(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("Evidence bundle must be a JSON object")
    transfers = bundle.get("transfers")
    report = bundle.get("investigation_report") or {}
    if not isinstance(transfers, list):
        raise ValueError("Evidence bundle must contain a transfers array")

    signal_map = {}
    for signal in report.get("behavioral_signals") or []:
        code = str(signal.get("code") or "review_signal")
        for evidence in signal.get("evidence") or []:
            tx_hash = evidence.get("tx_hash")
            if tx_hash:
                signal_map.setdefault(tx_hash, set()).add(code)

    rows = []
    seen = set()
    for transfer in transfers:
        if not isinstance(transfer, dict):
            continue
        identity = _identity(transfer)
        if identity in seen:
            continue
        seen.add(identity)
        case_id = "cs-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        tx_hash = str(transfer.get("hash") or "")
        signals = sorted(signal_map.get(tx_hash, set()))
        rows.append({
            "case_id": case_id,
            "tx_hash": tx_hash,
            "from_address": transfer.get("from_address") or "",
            "to_address": transfer.get("to_address") or "",
            "category": transfer.get("category") or "",
            "asset": transfer.get("asset") or "",
            "value": "" if transfer.get("value") is None else transfer.get("value"),
            "token_id": transfer.get("token_id") or "",
            "predicted_flag": "1" if signals else "0",
            "detector_signals": ";".join(signals),
            "actual_label": "",
            "label_source": "",
            "label_evidence_url": "",
            "label_notes": "",
        })
    return rows


def main(input_path, output_path):
    bundle = json.loads(Path(input_path).read_text(encoding="utf-8"))
    rows = build_rows(bundle)
    if not rows:
        raise ValueError("No transfer cases found in evidence bundle")
    with Path(output_path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} unlabeled cases to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python scripts/build_labeling_queue.py evidence.json labeling_queue.csv"
        )
    try:
        main(sys.argv[1], sys.argv[2])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
