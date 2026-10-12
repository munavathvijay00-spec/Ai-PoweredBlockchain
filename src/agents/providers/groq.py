"""
Groq LLM provider — cloud-based, fast, free tier.
"""
import asyncio
import time
from typing import Optional
from loguru import logger

try:
    from groq import AsyncGroq, RateLimitError
except ImportError:
    AsyncGroq = None
    RateLimitError = None


DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqProvider:
    """Groq provider for LLM inference."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if AsyncGroq is None:
            raise ImportError("groq package not installed. Run: pip install groq")
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self._cooldown_until = 0.0
        self._request_lock = asyncio.Lock()
        logger.info(f"🤖 Groq provider initialized (model={model})")

    async def generate(self, prompt: str, max_tokens: int = 250) -> str:
        """Generate text from a prompt."""
        # Serialize provider calls so a 429 blocks the rest of this process.
        # Do not retry quota errors: retries amplify the outage and token use.
        if time.monotonic() < self._cooldown_until:
            return ""
        async with self._request_lock:
            if time.monotonic() < self._cooldown_until:
                return ""
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:
                if RateLimitError is not None and isinstance(exc, RateLimitError):
                    self._cooldown_until = time.monotonic() + 180
                    logger.warning("Groq rate limit reached; pausing AI explanations for 180 seconds")
                    return ""
                logger.warning(f"Groq explanation unavailable ({type(exc).__name__})")
                return ""


_provider: Optional[GroqProvider] = None


def get_groq_provider(api_key: str, model: str = DEFAULT_MODEL) -> GroqProvider:
    global _provider
    if _provider is None or _provider.model != model:
        _provider = GroqProvider(api_key=api_key, model=model)
    return _provider