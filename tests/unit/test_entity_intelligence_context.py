from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.api.routes import _format_tx
from src.risk.evidence_v2 import assess_evidence
from src.risk.intelligence_signals import apply_verified_intelligence
from src.risk.official_entities import OFFICIAL_ENTITY_RECORDS, sync_official_entities


def _tx():
    return {
        "hash": "0x" + "1" * 64,
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "value": 10**18,
        "block_number": 123,
        "timestamp": datetime.now(timezone.utc),
        "risk_score": 0,
        "risk_factors": [],
        "ai_explanation": None,
    }


def test_protocol_entity_context_does_not_increase_risk():
    tx = _tx()
    matches = {
        tx["to_address"]: [{
            "source": "aave_official_docs",
            "entity_id": "aave-v3-ethereum-market",
            "entity_name": "Aave V3 Ethereum Market",
            "entity_type": "protocol",
            "confidence": 1.0,
            "source_url": "https://aave.com/docs/aave-v3/markets/data",
        }]
    }

    result = apply_verified_intelligence({"score": 10, "factors": []}, tx, matches)

    assert result["score"] == 10
    assert result["factors"] == []


def test_source_attributed_sanctions_match_is_provenance_rich_review_signal():
    tx = _tx()
    matches = {
        tx["to_address"]: [{
            "source": "ofac_sdn",
            "entity_id": "sdn-123",
            "entity_name": "Source-listed entity",
            "entity_type": "sanctions",
            "confidence": 1.0,
            "source_url": "https://ofac.treasury.gov/",
            "verified_at": datetime.now(timezone.utc),
        }]
    }

    result = apply_verified_intelligence({"score": 10, "factors": []}, tx, matches)

    assert result["score"] == 100
    factor = result["factors"][0]
    assert factor["factor"] == "verified_sanctions_match"
    assert factor["source"] == "ofac_sdn"
    assert factor["source_url"].startswith("https://")
    assert factor["matched_role"] == "recipient"
    assert "not proof" in factor["reason"].lower()


def test_verified_entity_factor_is_not_mixed_with_unverified_heuristics():
    assessment = assess_evidence([{
        "factor": "source_attributed_risk_entity_match",
        "reason": "Exact source-attributed address match",
        "source": "independent-source",
        "source_url": "https://example.org/evidence",
        "entity_name": "Example labelled address",
        "entity_type": "phishing",
        "matched_address": "0x" + "c" * 40,
        "matched_role": "recipient",
    }], "0x" + "2" * 64)

    assert assessment["assessment"] == "review"
    assert len(assessment["verified_entity_indicators"]) == 1
    assert assessment["unverified_indicators"] == []
    assert assessment["probability"] is None


def test_transaction_response_exposes_current_entity_context_without_calling_it_ownership():
    row = _tx()
    entity_matches = {
        row["to_address"]: [{
            "source": "lido_official_docs",
            "entity_id": "lido-steth",
            "entity_name": "Lido stETH / staking pool",
            "entity_type": "protocol",
            "confidence": 1.0,
            "source_url": "https://docs.lido.fi/deployed-contracts/",
            "attribution_scope": "address",
            "evidence": {"publisher": "Lido"},
        }]
    }

    response = _format_tx(row, entity_matches)

    assert response.entity_context["recipient"][0]["entity_name"].startswith("Lido")
    assert response.entity_context["status"] == "source_attributed_matches"
    assert "ownership" in response.entity_context["recipient"][0]["warning"].lower()


def test_official_registry_is_small_exact_and_source_cited():
    addresses = [row["address"] for row in OFFICIAL_ENTITY_RECORDS]
    assert len(addresses) == len(set(addresses))
    assert len(addresses) >= 5
    for row in OFFICIAL_ENTITY_RECORDS:
        assert row["address"].startswith("0x") and len(row["address"]) == 42
        assert row["confidence"] == 1.0
        assert row["source_url"].startswith("https://")
        assert row["entity_type"] in {"protocol", "contract"}


@pytest.mark.asyncio
async def test_official_registry_sync_is_additive_and_bounded():
    db = AsyncMock()
    db.fetchval.return_value = True

    count = await sync_official_entities(db)

    assert count == len(OFFICIAL_ENTITY_RECORDS)
    assert db.execute.await_count == len(OFFICIAL_ENTITY_RECORDS)
