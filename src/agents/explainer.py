"""
AI-powered transaction explainer.
Supports multiple LLM providers: Ollama (local) and Groq (cloud).
"""
import asyncio
import httpx
from typing import Dict, List, Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings


def evidence_explanation(tx: Dict, factors: List[Dict]) -> str:
    """Evidence-based fallback; does not claim to be AI-generated."""
    score = max(0, min(100, int(tx.get("risk_score") or 0)))
    reasons = []
    for factor in factors or []:
        reason = str(factor.get("reason") or "").strip().rstrip(".")
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) == 3:
            break
    if reasons:
        details = "; ".join(reasons)
        return (
            f"Rule-based risk assessment: this transaction scored {score}/100. "
            f"Detected evidence: {details}. "
            "These indicators warrant review but do not independently prove wrongdoing."
        )
    return (
        f"Rule-based risk assessment: this transaction scored {score}/100. "
        "The available scoring data does not include a specific supporting factor; "
        "review the transaction details before drawing conclusions."
    )


class TransactionExplainer:
    """Generates plain-English explanations for risky transactions."""

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.llm_provider
        self.model = self.settings.llm_model
        self.ollama_url = self.settings.ollama_url
        self.enabled = True
        self._semaphore = asyncio.Semaphore(3)
        logger.info(
            f"🧠 Explainer initialized "
            f"(provider={self.provider}, model={self.model})"
        )

    def _build_prompt(self, tx: Dict, factors: List[Dict]) -> str:
        """Build a structured prompt from transaction data + risk factors."""
        value_eth = int(tx.get('value') or 0) / 10**18

        factor_lines = []
        for f in (factors or []):
            factor_lines.append(
                f"- {f.get('factor', 'unknown')}: "
                f"{f.get('reason', 'no reason')} "
                f"(+{f.get('points', 0)} points)"
            )
        factors_text = "\n".join(factor_lines) if factor_lines else "- No specific factors"

        return f"""You are a blockchain security analyst. Explain to a non-technical user why this Ethereum transaction was flagged as risky. Use exactly 2-3 sentences.

Transaction data:
- Amount: {value_eth:.4f} ETH
- From address: {str(tx.get('from_address') or 'unknown')[:10]}...
- To address: {str(tx.get('to_address') or 'unknown')[:10]}...
- Block number: {tx.get('block_number', 0)}
- Risk score: {tx.get('risk_score', 0)}/100

Detected risk factors:
{factors_text}

Write a clear, specific explanation. Avoid technical jargon."""

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama's local API."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 200, "top_p": 0.9},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json().get("response", "").strip()

    async def _call_groq(self, prompt: str) -> Optional[str]:
        """Call Groq's cloud API."""
        from src.agents.providers.groq import get_groq_provider
        provider = get_groq_provider(
            api_key=self.settings.groq_api_key,
            model=self.settings.llm_model,
        )
        return await provider.generate(prompt)

    async def explain(self, tx: Dict, factors: List[Dict]) -> str:
        """Prefer AI wording, but always return a clearly labeled evidence fallback."""
        fallback = evidence_explanation(tx, factors)
        try:
            prompt = self._build_prompt(tx, factors)
            async with self._semaphore:
                if self.provider == "ollama":
                    explanation = await self._call_ollama(prompt)
                elif self.provider == "groq":
                    if not self.settings.groq_api_key or self.settings.groq_api_key == "not-set":
                        return fallback
                    explanation = await self._call_groq(prompt)
                else:
                    return fallback
            return explanation.strip() if isinstance(explanation, str) and explanation.strip() else fallback
        except Exception as exc:
            logger.warning(f"AI explanation unavailable ({type(exc).__name__}); using rule-based evidence")
            return fallback


_explainer: Optional[TransactionExplainer] = None


def get_explainer() -> TransactionExplainer:
    global _explainer
    if _explainer is None:
        _explainer = TransactionExplainer()
    return _explainer