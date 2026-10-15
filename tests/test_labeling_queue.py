"""Tests that the legacy labeling entrypoint cannot leak detector output to labelers."""
import unittest

from scripts.build_labeling_queue import build_rows


class LabelingQueueTests(unittest.TestCase):
    def test_labeler_rows_never_include_detector_output(self):
        tx_hash = "0x" + "1" * 64
        bundle = {
            "transfers": [{
                "hash": tx_hash,
                "from_address": "0x" + "a" * 40,
                "to_address": "0x" + "b" * 40,
                "category": "erc20",
                "asset": "USDC",
                "value": 125.0,
            }],
            "investigation_report": {
                "behavioral_signals": [{
                    "code": "repeated_pair",
                    "evidence": [{"tx_hash": tx_hash}],
                }]
            },
        }
        rows = build_rows(bundle)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("predicted_flag", rows[0])
        self.assertNotIn("detector_signals", rows[0])
        self.assertNotIn("actual_label", rows[0])
        self.assertTrue(rows[0]["case_id"].startswith("cs-"))

    def test_unflagged_transfer_is_not_presented_as_benign_ground_truth(self):
        bundle = {
            "transfers": [{
                "hash": "0x" + "2" * 64,
                "from_address": "0x" + "a" * 40,
                "to_address": "0x" + "c" * 40,
                "category": "external",
                "asset": "ETH",
                "value": 0.25,
            }],
            "investigation_report": {"behavioral_signals": []},
        }
        row = build_rows(bundle)[0]
        self.assertNotIn("predicted_flag", row)
        self.assertNotIn("actual_label", row)

    def test_duplicate_transfer_identity_is_deduplicated(self):
        transfer = {
            "hash": "0x" + "3" * 64,
            "from_address": "0x" + "a" * 40,
            "to_address": "0x" + "b" * 40,
            "category": "erc721",
            "asset": "NFT",
            "token_id": "42",
        }
        rows = build_rows({"transfers": [transfer, dict(transfer)]})
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
