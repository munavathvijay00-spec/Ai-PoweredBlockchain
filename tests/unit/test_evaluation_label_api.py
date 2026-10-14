from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.evaluation_routes import DetectionLabelInput, _normalize_label, run_evaluation


def test_self_labels_are_rejected():
    item = DetectionLabelInput(
        tx_hash="0x" + "a" * 64,
        label=1,
        label_source="ChainScope-risk-score",
        label_reference="case:123",
    )
    with pytest.raises(HTTPException) as exc:
        _normalize_label(item)
    assert exc.value.status_code == 422


def test_external_label_is_normalized():
    item = DetectionLabelInput(
        tx_hash="0x" + "A" * 64,
        label=1,
        label_source="External Analyst Review",
        label_reference="case:abc-123",
    )
    tx_hash, label, source, reference, notes = _normalize_label(item)
    assert tx_hash == "0x" + "a" * 64
    assert label == 1
    assert source == "External Analyst Review"
    assert reference == "case:abc-123"
    assert notes is None


@pytest.mark.asyncio
async def test_evaluation_deduplicates_agreeing_sources_by_transaction():
    repo = AsyncMock()
    repo.db.fetchval.side_effect = [True, 77]
    tx_hash = "0x" + "b" * 64
    factor = {"factor": "bursty_activity", "reason": "Observed burst", "points": 20}
    repo.db.fetch.return_value = [
        {
            "id": 1,
            "tx_hash": tx_hash,
            "label": 1,
            "label_source": "source-a",
            "label_reference": "case:a",
            "risk_score": 35,
            "risk_factors": [factor],
        },
        {
            "id": 2,
            "tx_hash": tx_hash,
            "label": 1,
            "label_source": "source-b",
            "label_reference": "case:b",
            "risk_score": 35,
            "risk_factors": [factor],
        },
    ]

    result = await run_evaluation(threshold=20, repo=repo)

    assert result["measured"] is True
    assert result["metrics"]["sample_size"] == 1
    assert result["metrics"]["raw_label_rows"] == 2
    assert result["metrics"]["unique_labeled_transactions"] == 1
    assert result["label_sources"] == ["source-a", "source-b"]


@pytest.mark.asyncio
async def test_evaluation_refuses_conflicting_labels():
    repo = AsyncMock()
    repo.db.fetchval.return_value = True
    tx_hash = "0x" + "c" * 64
    repo.db.fetch.return_value = [
        {
            "id": 1,
            "tx_hash": tx_hash,
            "label": 1,
            "label_source": "source-a",
            "label_reference": "case:a",
            "risk_score": 35,
            "risk_factors": [],
        },
        {
            "id": 2,
            "tx_hash": tx_hash,
            "label": 0,
            "label_source": "source-b",
            "label_reference": "case:b",
            "risk_score": 35,
            "risk_factors": [],
        },
    ]

    with pytest.raises(HTTPException) as exc:
        await run_evaluation(threshold=20, repo=repo)
    assert exc.value.status_code == 409
    assert "Conflicting independent labels" in exc.value.detail
