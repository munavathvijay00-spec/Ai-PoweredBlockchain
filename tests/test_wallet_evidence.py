import unittest
from scripts.verify_wallet_evidence import verify

class EvidenceTests(unittest.TestCase):
    def test_rejects_empty_bundle(self):
        self.assertEqual(verify({})["status"], "invalid")

    def test_rejects_wrong_network(self):
        self.assertIn("Unexpected chain", verify({"chain": "unknown"})["errors"])

if __name__ == "__main__":
    unittest.main()
