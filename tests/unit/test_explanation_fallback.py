"""Guaranteed explanation behavior without LLM access."""
import pytest
from unittest.mock import AsyncMock
from src.agents.explainer import TransactionExplainer, evidence_explanation


def test_evidence_fallback_includes_score_and_reason():
    result = evidence_explanation(
        {"risk_score": 85},
        [{"factor": "verified_sanctions_match", "reason": "Exact Ethereum address match in OFAC SDN sanctions data"}],
    )
    assert "Rule-based" in result
    assert "85/100" in result
    assert "OFAC SDN" in result
    assert "do not independently prove wrongdoing" in result


def test_empty_factors_do_not_invent_evidence():
    result = evidence_explanation({"risk_score": 25}, [])
    assert "does not include a specific supporting factor" in result


@pytest.mark.asyncio
async def test_explainer_falls_back_on_provider_failure():
    explainer = object.__new__(TransactionExplainer)
    import asyncio
    explainer._semaphore = asyncio.Semaphore(3)
    explainer.provider = "ollama"
    explainer._call_ollama = AsyncMock(side_effect=RuntimeError("offline"))
    explainer._build_prompt = lambda tx, factors: "prompt"
    result = await explainer.explain({"risk_score": 30}, [{"reason": "Unusual transfer size"}])
    assert "Rule-based" in result
    assert "Unusual transfer size" in result


@pytest.mark.asyncio
async def test_ai_explanation_used_only_when_grounded():
    explainer = object.__new__(TransactionExplainer)
    import asyncio
    explainer._semaphore = asyncio.Semaphore(3)
    explainer.provider = "ollama"
    explainer._call_ollama = AsyncMock(return_value="This transaction scored 30/100 because an unusual transfer size was detected. This is a review indicator, not proof of wrongdoing.")
    explainer._build_prompt = lambda tx, factors: "prompt"
    result = await explainer.explain({"risk_score": 30}, [{"reason": "Unusual transfer size"}])
    assert result.startswith("Grounded AI explanation:")
    assert "30/100" in result
    assert "Unusual transfer size".lower() in result.lower()


@pytest.mark.asyncio
async def test_ai_is_skipped_without_supporting_factors():
    explainer = object.__new__(TransactionExplainer)
    import asyncio
    explainer._semaphore = asyncio.Semaphore(3)
    explainer.provider = "ollama"
    explainer._call_ollama = AsyncMock(return_value="This transaction looks suspicious.")
    explainer._build_prompt = lambda tx, factors: "prompt"
    result = await explainer.explain({"risk_score": 30}, [])
    assert result.startswith("Rule-based risk assessment:")
    assert "does not include a specific supporting factor" in result
    explainer._call_ollama.assert_not_awaited()
