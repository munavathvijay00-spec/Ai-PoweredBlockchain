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
async def test_ai_explanation_used_when_available():
    explainer = object.__new__(TransactionExplainer)
    import asyncio
    explainer._semaphore = asyncio.Semaphore(3)
    explainer.provider = "ollama"
    explainer._call_ollama = AsyncMock(return_value="AI explanation")
    explainer._build_prompt = lambda tx, factors: "prompt"
    assert await explainer.explain({"risk_score": 30}, []) == "AI explanation"
