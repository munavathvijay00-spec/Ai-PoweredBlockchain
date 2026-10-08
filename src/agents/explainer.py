"""
AI-powered transaction explainer.
Supports multiple LLM providers: Ollama (local) and Groq (cloud).
"""
import httpx
from typing import Dict, List, Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings


class TransactionExplainer:
    """Generates plain-English explanations for risky transactions."""

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.llm_provider
        self.model = self.settings.llm_model
        self.ollama_url = self.settings.ollama_url
        self.enabled = True
        logger.info(
            f"🧠 Explainer initialized "
            f"(provider={self.provider}, model={self.model})"
        )

    def _build_prompt(self, tx: Dict, factors: List[Dict]) -> str:
        """Build a structured prompt from transaction data + risk factors."""
        value_eth = tx['value'] / 10**18
        usd_approx = value_eth * 2500

        factor_lines = []
        for f in factors:
            factor_lines.append(
                f"- {f.get('factor', 'unknown')}: "
                f"{f.get('reason', 'no reason')} "
                f"(+{f.get('points', 0)} points)"
            )
        factors_text = "\n".join(factor_lines) if factor_lines else "- No specific factors"

        return f"""You are a blockchain security analyst. Explain to a non-technical user why this Ethereum transaction was flagged as risky. Use exactly 2-3 sentences.

Transaction data:
- Amount: {value_eth:.4f} ETH (approximately ${usd_approx:,.0f} USD)
- From address: {tx.get('from_address', 'unknown')[:10]}...
- To address: {tx.get('to_address', 'unknown')[:10]}...
- Block number: {tx.get('block_number', 0)}
- Risk score: {tx.get('risk_score', 0)}/100

Detected risk factors:
{factors_text}

Write a clear, specific explanation. Avoid technical jargon."""

    # ---------- Ollama (local) ----------

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

    # ---------- Groq (cloud) ----------

    async def _call_groq(self, prompt: str) -> Optional[str]:
        """Call Groq's cloud API."""
        from src.agents.providers.groq import get_groq_provider
        provider = get_groq_provider(self.settings.groq_api_key)
        return await provider.generate(prompt)

    # ---------- Main entry point ----------

    async def explain(self, tx: Dict, factors: List[Dict]) -> Optional[str]:
        """Generate a plain-English explanation. Returns None if provider unavailable."""
        if not self.enabled:
            return None

        try:
            prompt = self._build_prompt(tx, factors)

            if self.provider == "ollama":
                explanation = await self._call_ollama(prompt)
            elif self.provider == "groq":
                explanation = await self._call_groq(prompt)
            else:
                logger.warning(f"Provider '{self.provider}' not implemented")
                return None

            return explanation or None

        except Exception as e:
            logger.warning(f"Explainer unavailable ({type(e).__name__}): {e}. Disabling.")
            self.enabled = False
            return None


# Singleton
_explainer: Optional[TransactionExplainer] = None


def get_explainer() -> TransactionExplainer:
    """Get or create the global explainer instance."""
    global _explainer
    if _explainer is None:
        _explainer = TransactionExplainer()
    return _explainer