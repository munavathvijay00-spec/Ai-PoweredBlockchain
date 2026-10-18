"""Regression tests for safety-critical evidence and evaluation behavior.

Run: python -m unittest discover -s tests -p 'test_hardening_contracts.py'
"""
import unittest
from src.agents.evidence_contract import build_evidence_contract, validate_claims_payload
from src.risk.evaluation import evaluate_predictions


class GroundingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.contract = build_evidence_contract(
            {"hash": "0x" + "a" * 64, "block_number": 123, "risk_score": 25},
            [{"factor": "value", "reason": "Observed amount exceeds configured threshold", "points": 25}],
        )

    def test_invented_numbers_fail_closed(self):
        payload = {
            "summary": {"text": "Observed block number is 999", "evidence_ids": ["E2"]},
            "claims": [], "uncertainty": "Indicators do not prove wrongdoing",
        }
        self.assertFalse(validate_claims_payload(payload, self.contract)["grounded"])

    def test_uncited_claims_fail_closed(self):
        payload = {
            "summary": {"text": "A transaction was recorded", "evidence_ids": []},
            "claims": [], "uncertainty": "Indicators do not prove wrongdoing",
        }
        self.assertFalse(validate_claims_payload(payload, self.contract)["grounded"])

    def test_uncertainty_cannot_assert_fraud(self):
        payload = {
            "summary": {"text": "Observed block number is 123", "evidence_ids": ["E2"]},
            "claims": [], "uncertainty": "Confirmed fraud, absolutely.",
        }
        self.assertFalse(validate_claims_payload(payload, self.contract)["grounded"])


class IndependentEvaluationTests(unittest.TestCase):
    def test_abstentions_reduce_operational_recall(self):
        metrics = evaluate_predictions([
            {"case_id": "one", "label": 1, "prediction": 1},
            {"case_id": "two", "label": 1, "prediction": "abstain"},
            {"case_id": "three", "label": 0, "prediction": 0},
        ])
        self.assertEqual(metrics["recall"], .5)
        self.assertAlmostEqual(metrics["decision_coverage"], 2 / 3)
        self.assertFalse(metrics["calibrated"])

    def test_duplicate_case_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_predictions([
                {"case_id": "a", "label": 1, "prediction": 1},
                {"case_id": "a", "label": 0, "prediction": 0},
            ])


if __name__ == "__main__":
    unittest.main()
