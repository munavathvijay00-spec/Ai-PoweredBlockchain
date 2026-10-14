import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.ai_audit import ai_quality_summary, provider_configuration
from src.agents.explainer import TransactionExplainer, evidence_explanation, grounding_report


def _tx():
    return {
        "hash": "0x" + "1" * 64,
        "from_address": "0x" + "a" * 40,
        "to_address": "0x" + "b" * 40,
        "value": 2 * 10**18,
        "block_number": 123456,
        "risk_score": 30,
    }


def _factors():
    return [{"factor": "bursty_activity", "points": 25, "reason": "Observed burst in retained evidence"}]


def test_grounding_rejects_generic_same_score_text_when_transaction_context_exists():
    tx = _tx()
    baseline = evidence_explanation(tx, _factors())
    candidate = (
        "This transaction scored 30/100 because an observed burst warrants review [E1]. "
        "The signal is not proof of wrongdoing."
    )

    report = grounding_report(candidate, baseline, tx)

    assert report["grounded"] is False
    assert "missing_transaction_specific_context" in report["reasons"]


def test_grounding_accepts_transaction_specific_fact():
    tx = _tx()
    baseline = evidence_explanation(tx, _factors())
    candidate = (
        "For block 123,456, the transaction scored 30/100 because an observed burst warrants review [E1]. "
        "The signal is not proof of wrongdoing."
    )

    report = grounding_report(candidate, baseline, tx)

    assert report["grounded"] is True
    assert report["checks"]["transaction_specific"] is True


@pytest.mark.asyncio
async def test_explain_with_audit_proves_when_real_ai_is_not_configured():
    explainer = object.__new__(TransactionExplainer)
    explainer._semaphore = asyncio.Semaphore(1)
    explainer.provider = "groq"
    explainer.model = "openai/gpt-oss-20b"
    explainer.settings = SimpleNamespace(groq_api_key="not-set")
    explainer._call_groq = AsyncMock()

    result = await explainer.explain_with_audit(_tx(), _factors())

    assert result["status"] == "provider_not_configured"
    assert result["ai_used"] is False
    assert result["explanation"].startswith("Evidence-based transaction review:")
    explainer._call_groq.assert_not_awaited()


@pytest.mark.asyncio
async def test_explain_with_audit_marks_only_grounded_model_output_as_real_ai():
    tx = _tx()
    explainer = object.__new__(TransactionExplainer)
    explainer._semaphore = asyncio.Semaphore(1)
    explainer.provider = "ollama"
    explainer.model = "test-model"
    explainer._call_ollama = AsyncMock(return_value=(
        "For block 123,456, this transaction scored 30/100 because an observed burst warrants review [E1]. "
        "The signal is not proof of wrongdoing."
    ))
    explainer._build_prompt = lambda tx, factors: "prompt"

    result = await explainer.explain_with_audit(tx, _factors())

    assert result["status"] == "grounded_ai"
    assert result["ai_used"] is True
    assert result["grounding_report"]["grounded"] is True
    assert result["explanation"].startswith("Grounded AI explanation:")


@pytest.mark.asyncio
async def test_ai_quality_summary_does_not_call_grounding_rate_detection_accuracy():
    db = AsyncMock()
    db.fetchrow.return_value = {
        "total_runs": 10,
        "grounded_ai_runs": 6,
        "grounding_rejections": 2,
        "provider_no_output": 2,
        "provider_not_configured": 0,
        "abstained_no_evidence": 0,
        "last_grounded_at": None,
        "last_attempt_at": None,
    }

    summary = await ai_quality_summary(db)

    assert summary["model_attempts"] == 10
    assert summary["grounding_acceptance_rate"] == pytest.approx(0.6)
    assert "not transaction-detection accuracy" in summary["metric_scope"]
