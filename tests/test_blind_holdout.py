import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_blind_holdout import _verify_manifest, join_rows


LABEL_FIELDS = [
    "case_id",
    "actual_label",
    "label_source",
    "label_evidence_url",
    "label_notes",
    "adjudicator_id",
    "adjudicated_at",
]
PRED_FIELDS = ["case_id", "predicted_flag", "detector_signals"]


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def labeled(case_id, actual="1"):
    return {
        "case_id": case_id,
        "actual_label": actual,
        "label_source": "independent-review",
        "label_evidence_url": "https://example.test/evidence",
        "label_notes": "",
        "adjudicator_id": "reviewer-1",
        "adjudicated_at": "2026-10-15T00:00:00+00:00",
    }


class BlindHoldoutTests(unittest.TestCase):
    def test_join_requires_exact_case_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = root / "labels.csv"
            preds = root / "predictions.csv"
            write_csv(labels, LABEL_FIELDS, [labeled("case-a")])
            write_csv(preds, PRED_FIELDS, [{"case_id": "case-b", "predicted_flag": "1", "detector_signals": "rule"}])
            with self.assertRaises(ValueError):
                join_rows(str(labels), str(preds))

    def test_join_requires_label_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = root / "labels.csv"
            preds = root / "predictions.csv"
            row = labeled("case-a")
            row["label_source"] = ""
            write_csv(labels, LABEL_FIELDS, [row])
            write_csv(preds, PRED_FIELDS, [{"case_id": "case-a", "predicted_flag": "1", "detector_signals": "rule"}])
            with self.assertRaises(ValueError):
                join_rows(str(labels), str(preds))

    def test_manifest_detects_prediction_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preds = root / "predictions.csv"
            manifest = root / "manifest.json"
            write_csv(preds, PRED_FIELDS, [{"case_id": "case-a", "predicted_flag": "1", "detector_signals": "rule"}])
            digest = hashlib.sha256(preds.read_bytes()).hexdigest()
            manifest.write_text(json.dumps({
                "dataset_id": "dataset-1",
                "labeling_protocol": "blind_independent_adjudication",
                "leakage_control": {
                    "labels_file_contains_predictions": False,
                    "cases_file_contains_detector_signals": False,
                },
                "files": {"predictions.csv": digest},
            }), encoding="utf-8")
            preds.write_text(preds.read_text(encoding="utf-8").replace(",1,", ",0,"), encoding="utf-8")
            with self.assertRaises(ValueError):
                _verify_manifest(str(manifest), str(preds))

    def test_valid_join_produces_only_evaluation_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = root / "labels.csv"
            preds = root / "predictions.csv"
            write_csv(labels, LABEL_FIELDS, [labeled("case-a", "1"), labeled("case-b", "0")])
            write_csv(preds, PRED_FIELDS, [
                {"case_id": "case-a", "predicted_flag": "1", "detector_signals": "rule-a"},
                {"case_id": "case-b", "predicted_flag": "0", "detector_signals": ""},
            ])
            joined = join_rows(str(labels), str(preds))
            self.assertEqual(joined, [
                {"case_id": "case-a", "actual_label": "1", "predicted_flag": "1"},
                {"case_id": "case-b", "actual_label": "0", "predicted_flag": "0"},
            ])


if __name__ == "__main__":
    unittest.main()
