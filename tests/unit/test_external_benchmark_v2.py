from unittest.mock import AsyncMock

import pytest

from src.api.evaluation_routes import _case_has_source_leakage, _publication_gate
from src.risk.external_benchmark import evaluate_external_benchmark


def test_publication_gate_requires_minimum_sample_and_both_classes():
    small = _publication_gate({"sample_size": 20, "positive_support": 10, "negative_support": 10})
    assert small["publishable"] is False
    assert "sample_size_below_30" in small["reasons"]

    imbalanced = _publication_gate({"sample_size": 40, "positive_support": 5, "negative_support": 35})
    assert imbalanced["publishable"] is False
    assert "positive_support_below_10" in imbalanced["reasons"]

    ready = _publication_gate({"sample_size": 40, "positive_support": 20, "negative_support": 20})
    assert ready["publishable"] is True
    assert ready["reasons"] == []


def test_label_source_reuse_is_detected_as_evaluation_leakage():
    label_rows = [{
        "label_source": "OFAC SDN ETH",
        "label_reference": "https://ofac.treasury.gov/sanctions-list-data-formats-data-schemas",
    }]
    factors = [{
        "factor": "verified_sanctions_match",
        "source": "OFAC_SDN_ETH",
        "source_url": "https://ofac.treasury.gov/sanctions-list-data-formats-data-schemas",
    }]

    assert _case_has_source_leakage(label_rows, factors) is True


def test_independent_source_does_not_trigger_leakage():
    label_rows = [{
        "label_source": "External Analyst Review",
        "label_reference": "https://independent.example/case/123",
    }]
    factors = [{
        "factor": "bursty_activity",
        "source": "chainscope-behavior-window",
        "source_url": "https://etherscan.io/tx/0xabc",
    }]

    assert _case_has_source_leakage(label_rows, factors) is False


@pytest.mark.asyncio
async def test_external_benchmark_keeps_amount_only_cases_as_product_abstentions():
    db = AsyncMock()
    db.fetch.return_value = [
        {
            "source_row_idx": 1,
            "tx_hash": "0x" + "1" * 64,
            "label": 1,
            "from_address": "0x" + "a" * 40,
            "to_address": "0x" + "b" * 40,
            "value_wei_text": str(2_000 * 10**18),
            "gas": 21000,
            "gas_price_text": "1000000000",
            "block_timestamp_text": "1700000000",
            "block_number": 123,
            "category": "scam",
        },
        {
            "source_row_idx": 2,
            "tx_hash": "0x" + "2" * 64,
            "label": 0,
            "from_address": "0x" + "c" * 40,
            "to_address": "0x" + "d" * 40,
            "value_wei_text": str(1 * 10**18),
            "gas": 21000,
            "gas_price_text": "1000000000",
            "block_timestamp_text": "1700000001",
            "block_number": 124,
            "category": "none",
        },
    ]
    scorer = AsyncMock()
    scorer.score_transaction.side_effect = [
        {
            "score": 40,
            "factors": [{
                "factor": "whale_transaction",
                "points": 40,
                "reason": "2,000 ETH transfer — whale amount tier",
            }],
        },
        {
            "score": 10,
            "factors": [{
                "factor": "medium_transaction",
                "points": 10,
                "reason": "1 ETH transfer",
            }],
        },
    ]

    result = await evaluate_external_benchmark(db, scorer, threshold=20)

    assert result["measured"] is True
    assert result["sample_size"] == 2
    assert result["policy_metrics"]["abstentions"] == 2
    assert result["policy_metrics"]["decision_coverage"] == 0
    assert result["raw_numeric_score_metrics"]["confusion_matrix"]["tp"] == 1
    assert result["raw_numeric_score_metrics"]["confusion_matrix"]["tn"] == 1
    assert result["representative"] is False
    assert "transaction-native fields only" in result["evaluation_scope"]
