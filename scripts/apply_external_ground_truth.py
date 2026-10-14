"""Apply externally sourced address labels to ChainScope transfer cases.

This script intentionally does NOT convert unmatched transfers into negatives.
Unmatched cases are emitted as `unscored` until independently adjudicated.

Usage:
  python scripts/apply_external_ground_truth.py \
    evaluation/external_ground_truth_v1.json \
    evaluation/holdout-v1/cases.csv \
    evaluation/holdout-v1/external_labels.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


def _address(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text.startswith("0x") else ""


def load_registry(path: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = {
        str(item["source_id"]): item
        for item in payload.get("sources", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    labels: dict[str, dict[str, Any]] = {}
    for item in payload.get("address_labels", []):
        if not isinstance(item, dict):
            continue
        address = _address(item.get("address"))
        if not address:
            continue
        if address in labels:
            raise ValueError(f"Duplicate external address label: {address}")
        source_id = str(item.get("source_id") or "")
        if source_id not in sources:
            raise ValueError(f"Unknown source_id {source_id!r} for {address}")
        if item.get("label") not in {0, 1}:
            raise ValueError(f"External label for {address} must be 0 or 1")
        labels[address] = item
    return labels, sources


def apply_registry(registry_path: str, cases_path: str) -> list[dict[str, str]]:
    labels, sources = load_registry(registry_path)
    with Path(cases_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"case_id", "from_address", "to_address"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Cases CSV must contain {sorted(required)}")

        output: list[dict[str, str]] = []
        for row in reader:
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                raise ValueError("Blank case_id in cases CSV")
            from_address = _address(row.get("from_address"))
            to_address = _address(row.get("to_address"))
            matches = [labels[a] for a in {from_address, to_address} if a in labels]

            if not matches:
                output.append({
                    "case_id": case_id,
                    "actual_label": "unscored",
                    "label_source": "",
                    "label_evidence_url": "",
                    "label_notes": "No independent external ground-truth match; do not treat as negative.",
                    "adjudicator_id": "external-registry-v1",
                    "adjudicated_at": "",
                })
                continue

            distinct_labels = {int(match["label"]) for match in matches}
            if len(distinct_labels) != 1:
                raise ValueError(f"Conflicting external labels for case {case_id}")
            label = distinct_labels.pop()
            source_ids = sorted({str(match["source_id"]) for match in matches})
            incidents = sorted({str(match.get("incident") or "") for match in matches if match.get("incident")})
            attributions = sorted({str(match.get("attribution") or "") for match in matches if match.get("attribution")})
            urls = sorted({str(sources[source_id].get("url") or "") for source_id in source_ids})

            output.append({
                "case_id": case_id,
                "actual_label": str(label),
                "label_source": ";".join(source_ids),
                "label_evidence_url": ";".join(urls),
                "label_notes": "External address match. incidents=" + ",".join(incidents) + "; attribution=" + ",".join(attributions),
                "adjudicator_id": "external-registry-v1",
                "adjudicated_at": "registry_source_date",
            })
    return output


def main(registry_path: str, cases_path: str, output_path: str) -> None:
    rows = apply_registry(registry_path, cases_path)
    fields = [
        "case_id", "actual_label", "label_source", "label_evidence_url",
        "label_notes", "adjudicator_id", "adjudicated_at",
    ]
    with Path(output_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    scored = sum(row["actual_label"] in {"0", "1"} for row in rows)
    print(f"Wrote {len(rows)} cases: {scored} externally scored, {len(rows) - scored} unscored")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python scripts/apply_external_ground_truth.py registry.json cases.csv output.csv")
    try:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
