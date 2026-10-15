"""Deprecated compatibility entrypoint for building human labeling material.

The old implementation placed detector predictions beside blank ground-truth columns,
which can bias adjudicators. This module now exposes only labeler-safe case rows and the
CLI delegates to the blind evaluation package builder.

Usage:
    python scripts/build_labeling_queue.py evidence.json out_dir

The output directory contains cases.csv, labels.csv, predictions.csv and manifest.json.
Only cases.csv + labels.csv should be given to adjudicators. Keep predictions.csv sealed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.build_blind_evaluation_set import build_package, main as build_blind_package


def build_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return labeler-visible factual case material only.

    Kept for compatibility with callers of the former queue builder. Detector predictions
    and detector signals are intentionally absent.
    """
    cases, _labels, _predictions = build_package(bundle)
    return cases


def main(input_path: str, output_dir: str) -> None:
    # Validate early for a clearer compatibility error, then use the canonical blind builder.
    json.loads(Path(input_path).read_text(encoding="utf-8"))
    build_blind_package(input_path, output_dir)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/build_labeling_queue.py evidence.json out_dir")
    try:
        main(sys.argv[1], sys.argv[2])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
