"""Grounded transaction explanations with optional LLM wording.

The model is never allowed to become a source of facts. Stored risk factors remain the
source of truth; any model-generated wording that introduces unsupported claims or
numbers is rejected and replaced by the deterministic evidence explanation.
"""
import asyncio
import re
from typing import Dict, List, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings

_OVERCLAIM_PHRASES = (
    "definitely", "certainly", "proves", "proof of wrongdoing", "confirmed fraud",
    "confirmed illicit", "is fraudulent", "is a scam", "criminal activity",
    "money laundering", "stolen funds", "malicious actor",
)

_SENSITIVE_CLAIM_TERMS = (
    "mixer", "tornado", "sanction", "ofac", "hack", "hacker", "scam", "phishing",
    "stolen", "launder", "criminal", "fraud", "malicious", "exchange", "bridge",
    "darknet", "ransomware",
)


def _normalized_numbers(text: str) -> set[str]:
    """Extract claimed numbers while ignoring hexadecimal hashes/addresses."""
    without_hex = re.sub(r"0x[a-fA-F0-9]+", "", text or "")
    values = re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", without_hex)
    return {value.replace(",", "") for value in values}


def explanation_is_grounded(candidate: str, baseline: str) -> bool:
    """Reject LLM wording that adds facts not present in the deterministic baseline."""
    if not isinstance(candidate, str):
        return False
    text = candidate.strip()
    if len(text) < 20 or len(text) > 700:
        return False
    lowered = text.lower()
    baseline_lower = (baseline or "").lower()
    if any(phrase in lowered for phrase in _OVERCLAIM_PHRASES):
        return False
    for term in _SENSITIVE_CLAIM_TERMS:
        if term in lowered and term not in baseline_lower:
            return False
    if not _normalized_numbers(text).issubset(_normalized_numbers(baseline)):
        return False
    return True


def evidence_explanation(tx: Dict, factors: List[Dict]) -> str:
    """Deterministic explanation assembled only from stored scoring evidence."""
    score = max(0, min(100, int(tx.get("risk_score") or 0)))
    reasons: List[str] = []
    for factor in factors or []:
        reason = str(factor.get("reason") or "").strip().rstrip(".")
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) == 3:
            break
    if reasons:
        return (
            f"Evidence-based assessment: this transaction scored {score}/100. "
            f"Observed scoring signals: {'; '.join(reasons)}. "
            "These signals describe only the indexed evidence used by the scorer and do not establish intent or wrongdoing."
        )
    return (
        f"Evidence-based assessment: this transaction scored {score}/100. "
        "No specific supporting factor is stored for this score, so an AI conclusion would not be reliable. "
        "Review the raw transaction evidence before drawing conclusions."
    )


class TransactionExplainer:
    """Optionally rewrites a deterministic evidence explanation without adding facts."""

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.llm_provider
        self.model = self.settings.llm_model
        self.ollama_url = self.settings.ollama_url
        self._semaphore = asyncio.Semaphore(3)
        logger.info(f"🧠 Grounded explainer initialized (provider={self.provider}, model={self.model})")

    def _build_prompt(self, baseline: str) -> str:
        return f"""You are editing an evidence-grounded Ethereum transaction explanation.

SOURCE OF TRUTH:
{baseline}

Rules:
- Rewrite the source into at most 2 short sentences for a non-technical user.
- Use ONLY facts already present in SOURCE OF TRUTH.
- Keep the exact risk score and any numeric evidence unchanged.
- Do not infer identity, ownership, intent, fraud, sanctions, scams, hacks, theft, laundering, exchange usage, mixer usage, or historical behavior unless SOURCE OF TRUTH explicitly states it.
- Do not convert values to USD or add market prices.
- State that the signals are review indicators, not proof of wrongdoing.
- If a faithful rewrite is not possible, return exactly: UNSAFE_TO_REWRITE

Return only the explanation text."""

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def _call_ollama(self, prompt: str) -> str:
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 180, "top_p": 0.8},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json().get("response", "").strip()

    async def _call_groq(self, prompt: str) -> Optional[str]:
        from src.agents.providers.groq import get_groq_provider
        provider = get_groq_provider(api_key=self.settings.groq_api_key, model=self.settings.llm_model)
        return await provider.generate(prompt)

    async def explain(self, tx: Dict, factors: List[Dict]) -> str:
        """Return validated AI wording or the deterministic evidence fallback."""
        baseline = evidence_explanation(tx, factors)
        try:
            prompt = self._build_prompt(baseline)
            async with self._semaphore:
                if self.provider == "ollama":
                    candidate = await self._call_ollama(prompt)
                elif self.provider == "groq":
                    if not self.settings.groq_api_key or self.settings.groq_api_key == "not-set":
                        return baseline
                    candidate = await self._call_groq(prompt)
                else:
                    return baseline

            if not isinstance(candidate, str) or not candidate.strip() or candidate.strip() == "UNSAFE_TO_REWRITE":
                return baseline
            candidate = candidate.strip()
            if not explanation_is_grounded(candidate, baseline):
                logger.warning("Rejected ungrounded AI explanation; using deterministic evidence")
                return baseline
            return f"Grounded AI explanation: {candidate}"
        except Exception as exc:
            logger.warning(f"AI explanation unavailable ({type(exc).__name__}); using deterministic evidence")
            return baseline


_explainer: Optional[TransactionExplainer] = None


def get_explainer() -> TransactionExplainer:
    global _explainer
    if _explainer is None:
        _explainer = TransactionExplainer()
    return _explainer
