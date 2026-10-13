"""Tests for the offline, labeled detection evaluation utility.

Run: python -m unittest discover -s tests -p 'test_detection_evaluation.py'
"""
import unittest
from scripts.evaluate_detection import evaluate


def row(case_id, actual, predicted):
    return {"case_id": case_id, "actual_label": actual, "predicted_flag": predicted}


class EvaluationTests(unittest.TestCase):
    def test_confusion_matrix_and_metrics(self):
        result = evaluate([
            row("tp", "1", "1"), row("fp", "0", "1"),
            row("tn", "0", "0"), row("fn", "1", "0"),
        ])
        self.assertEqual(result["confusion_matrix"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1})
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["specificity"], 0.5)
        self.assertEqual(result["f1"], 0.5)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["false_positive_rate"], 0.5)
        self.assertEqual(result["false_negative_rate"], 0.5)
        self.assertEqual(result["positive_support"], 2)
        self.assertEqual(result["negative_support"], 2)

    def test_no_positive_predictions(self):
        result = evaluate([row("negative", "0", "0")])
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
        self.assertIsNone(result["f1"])
        self.assertEqual(result["specificity"], 1.0)
        self.assertEqual(result["false_positive_rate"], 0.0)
        self.assertIsNone(result["false_negative_rate"])

    def test_all_true_positives(self):
        result = evaluate([row("p1", "1", "1"), row("p2", "1", "1")])
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(result["false_negative_rate"], 0.0)
        self.assertIsNone(result["specificity"])
        self.assertIsNone(result["false_positive_rate"])

    def test_all_false_negatives(self):
        result = evaluate([row("p1", "1", "0")])
        self.assertEqual(result["recall"], 0.0)
        self.assertEqual(result["false_negative_rate"], 1.0)
        self.assertIsNone(result["precision"])
        self.assertEqual(result["f1"], 0.0)

    def test_duplicate_case_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([row("same", "1", "1"), row("same", "0", "0")])

    def test_non_binary_label_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([row("case", "fraud", "1")])

    def test_empty_identifier_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([row(" ", "1", "1")])


if __name__ == "__main__":
    unittest.main()
