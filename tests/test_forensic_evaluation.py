import unittest
from tools.forensic_evaluation import evaluate

class EvaluationTests(unittest.TestCase):
    def test_confusion_matrix_and_citations(self):
        cases = [
            {"ground_truth":1,"predicted":1,"claims":[{"supported":True,"cited_ids":["a"],"valid_ids":["a"],"material_evidence_ids":["a"]}]},
            {"ground_truth":0,"predicted":1,"claims":[{"supported":False,"cited_ids":["bad"],"valid_ids":["good"],"material_evidence_ids":["good"]}]},
            {"ground_truth":0,"predicted":0},
            {"ground_truth":1,"predicted":0},
        ]
        result = evaluate(cases)
        self.assertEqual(result["risk_detection"]["precision"], .5)
        self.assertEqual(result["risk_detection"]["recall"], .5)
        self.assertEqual(result["risk_detection"]["false_positive_rate"], .5)
        self.assertEqual(result["ai_findings"]["citation_precision"], .5)
        self.assertEqual(result["ai_findings"]["unsupported_claim_rate"], .5)

    def test_no_denominator_does_not_claim_perfect_score(self):
        result = evaluate([])
        self.assertIsNone(result["risk_detection"]["precision"])
        self.assertIsNone(result["ai_findings"]["citation_precision"])

    def test_rejects_non_binary_labels(self):
        with self.assertRaises(ValueError):
            evaluate([{"ground_truth":2,"predicted":1}])

if __name__ == "__main__":
    unittest.main()
