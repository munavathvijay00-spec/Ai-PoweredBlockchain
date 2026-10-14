from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.agents.enrichment_worker as worker


def _settings():
    return SimpleNamespace(ai_enrichment_batch_size=4, ai_enrichment_min_score=20)


@pytest.mark.asyncio
async def test_enrichment_skips_database_scan_when_provider_not_configured(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(worker, "get_settings", _settings)
    monkeypatch.setattr(
        worker,
        "provider_configuration",
        lambda: {
            "provider": "groq",
            "model": "openai/gpt-oss-20b",
            "provider_configured": False,
            "configuration_reason": "missing_groq_api_key_or_model",
        },
    )

    result = await worker.enrich_once(db)

    assert result["provider_configured"] is False
    assert result["selected"] == 0
    assert result["grounded_saved"] == 0
    db.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrichment_persists_only_accepted_grounded_ai(monkeypatch):
    tx_hash = "0x" + "1" * 64
    db = AsyncMock()
    db.fetch.return_value = [{
        "hash": tx_hash,
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "value": 10**18,
        "block_number": 123,
        "timestamp": None,
        "risk_score": 25,
        "risk_factors": [{
            "factor": "bursty_activity",
            "points": 25,
            "reason": "11 observed transfers in the recent retained window",
        }],
        "ai_explanation": None,
    }]
    monkeypatch.setattr(worker, "get_settings", _settings)
    monkeypatch.setattr(
        worker,
        "provider_configuration",
        lambda: {
            "provider": "groq",
            "model": "openai/gpt-oss-20b",
            "provider_configured": True,
            "configuration_reason": "configured",
        },
    )
    audit_recorder = AsyncMock()
    monkeypatch.setattr(worker, "record_ai_run", audit_recorder)

    explainer = AsyncMock()
    explainer.explain_with_audit.return_value = {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "status": "grounded_ai",
        "ai_used": True,
        "grounded": True,
        "explanation": "Grounded AI explanation: Transaction 0x111111111111 has a recorded review indicator [E1]; this does not prove wrongdoing.",
        "grounding_report": {"grounded": True},
    }

    result = await worker.enrich_once(db, explainer=explainer, limit=1)

    assert result["selected"] == 1
    assert result["grounded_saved"] == 1
    assert result["fallbacks"] == 0
    audit_recorder.assert_awaited_once()
    assert any(
        call.args and "UPDATE transactions" in call.args[0]
        for call in db.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_enrichment_audits_but_does_not_store_rejected_ai(monkeypatch):
    tx_hash = "0x" + "2" * 64
    db = AsyncMock()
    db.fetch.return_value = [{
        "hash": tx_hash,
        "from_address": "0x" + "c" * 40,
        "to_address": "0x" + "d" * 40,
        "value": 5 * 10**18,
        "block_number": 456,
        "timestamp": None,
        "risk_score": 25,
        "risk_factors": [{
            "factor": "bursty_activity",
            "points": 25,
            "reason": "11 observed transfers in the recent retained window",
        }],
        "ai_explanation": None,
    }]
    monkeypatch.setattr(worker, "get_settings", _settings)
    monkeypatch.setattr(
        worker,
        "provider_configuration",
        lambda: {
            "provider": "groq",
            "model": "openai/gpt-oss-20b",
            "provider_configured": True,
            "configuration_reason": "configured",
        },
    )
    audit_recorder = AsyncMock()
    monkeypatch.setattr(worker, "record_ai_run", audit_recorder)

    explainer = AsyncMock()
    explainer.explain_with_audit.return_value = {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "status": "grounding_rejected",
        "ai_used": False,
        "grounded": True,
        "explanation": "Evidence-based transaction review: fallback",
        "grounding_report": {"grounded": False, "reasons": ["unsupported_claim"]},
    }

    result = await worker.enrich_once(db, explainer=explainer, limit=1)

    assert result["grounded_saved"] == 0
    assert result["fallbacks"] == 1
    audit_recorder.assert_awaited_once()
    assert not any(
        call.args and "UPDATE transactions" in call.args[0]
        for call in db.execute.await_args_list
    )
