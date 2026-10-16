from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import _format_tx
from src.risk.intelligence_signals import enrich_with_verified_intelligence
from src.risk.official_entities import OFFICIAL_ENTITY_RECORDS, sync_official_entities


def _row(**overrides):
    base = {
        "hash": "0x" + "1" * 64,
        "block_number": 1,
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "value": "1",
        "gas": 21000,
        "gas_price": "1",
        "nonce": 1,
        "timestamp": None,
        "risk_score": 0,
        "risk_factors": [],
        "risk_explanation": None,
    }
    base.update(overrides)
    return base


def test_protocol_entity_context_does_not_increase_risk():
    tx = _row()
    matches = {
        tx["to_address"]: [{
            "source": "uniswap_official_deployments",
            "entity_id": "uniswap-v3-router",
            "entity_name": "Uniswap V3 SwapRouter",
            "entity_type": "protocol",
            "confidence": 1.0,
            "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        }]
    }

    result = enrich_with_verified_intelligence(tx, matches)
    assert result["risk_score"] == 0
    assert result["verified_entity_context"]["status"] == "source_attributed_matches"
    assert result["verified_entity_context"]["recipient"][0]["entity_name"] == "Uniswap V3 SwapRouter"


def test_source_attributed_sanctions_match_is_provenance_rich_review_signal():
    tx = _row()
    matches = {
        tx["from_address"]: [{
            "source": "ofac_sdn",
            "entity_id": "sdn-1",
            "entity_name": "OFAC SDN Ethereum address",
            "entity_type": "sanctions",
            "confidence": 1.0,
            "source_url": "https://ofac.treasury.gov/",
        }]
    }

    result = enrich_with_verified_intelligence(tx, matches)
    factor = result["risk_factors"][-1]
    assert factor["type"] == "verified_intelligence_match"
    assert factor["evidence"]["source"] == "ofac_sdn"
    assert factor["evidence"]["source_url"].startswith("https://")
    assert factor["requires_review"] is True


def test_verified_entity_factor_is_not_mixed_with_unverified_heuristics():
    tx = _row(risk_factors=[{"type": "large_transfer", "score": 20}])
    matches = {
        tx["to_address"]: [{
            "source": "circle_official_usdc",
            "entity_id": "circle-usdc-ethereum",
            "entity_name": "USDC on Ethereum",
            "entity_type": "token",
            "confidence": 1.0,
            "source_url": "https://www.circle.com/multi-chain-usdc/ethereum",
        }]
    }

    result = enrich_with_verified_intelligence(tx, matches)
    assert result["risk_factors"][0]["type"] == "large_transfer"
    assert result["verified_entity_context"]["recipient"][0]["entity_type"] == "token"


def test_transaction_response_exposes_current_entity_context_without_calling_it_ownership():
    row = _row(to_address="0xae7ab96520de3a18e5e111b5eaab095312d7fe84")
    match = {
        "source": "lido_official_docs",
        "entity_id": "lido-steth",
        "entity_name": "Lido stETH / staking pool",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
    }
    entity_matches = {row["to_address"]: [match]}

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
        # Exact token contracts are valid first-party entity records too; the
        # registry still requires exact addresses, first-party provenance, and
        # confidence=1.0 rather than inferred ownership labels.
        assert row["entity_type"] in {"protocol", "contract", "token"}


@pytest.mark.asyncio
async def test_official_registry_sync_is_additive_and_bounded():
    db = AsyncMock()
    db.fetchval.return_value = True

    count = await sync_official_entities(db)

    assert count == len(OFFICIAL_ENTITY_RECORDS)
    assert db.execute.await_count == len(OFFICIAL_ENTITY_RECORDS)
