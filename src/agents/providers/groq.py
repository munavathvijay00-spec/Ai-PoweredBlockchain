"""Groq LLM provider with bounded retries, cooldown, and observability."""
import asyncio
import time
from typing import Optional
from loguru import logger

try:
    from groq import AsyncGroq, RateLimitError
except ImportError:
    AsyncGroq = None
    RateLimitError = None

from src.metrics import (
    groq_requests_total,
    groq_request_duration_seconds,
    ai_request_duration_seconds,
)

DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if AsyncGroq is None:
            raise ImportError("groq package not installed")
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self._cooldown_until = 0.0
        self._request_lock = asyncio.Lock()
        logger.info(f"Groq provider initialized (model={model})")

    async def generate(self, prompt: str, max_tokens: int = 250) -> str:
        if time.monotonic() < self._cooldown_until:
            groq_requests_total.labels(status="cooldown").inc()
            return ""
        async with self._request_lock:
            if time.monotonic() < self._cooldown_until:
                groq_requests_total.labels(status="cooldown").inc()
                return ""
            started = time.monotonic()
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=max_tokens,
                )
                text = (response.choices[0].message.content or "").strip()
                groq_requests_total.labels(status="success").inc()
                return text
            except Exception as exc:
                if RateLimitError is not None and isinstance(exc, RateLimitError):
                    self._cooldown_until = time.monotonic() + 180
                    groq_requests_total.labels(status="rate_limited").inc()
                    logger.warning("Groq rate limit reached; pausing AI explanations for 180 seconds")
                    return ""
                groq_requests_total.labels(status="error").inc()
                logger.warning(f"Groq explanation unavailable ({type(exc).__name__})")
                return ""
            finally:
                elapsed = time.monotonic() - started
                groq_request_duration_seconds.observe(elapsed)
                ai_request_duration_seconds.labels(provider="groq").observe(elapsed)


_provider: Optional[GroqProvider] = None


def get_groq_provider(api_key: str, model: str = DEFAULT_MODEL) -> GroqProvider:
    global _provider
    if _provider is None or _provider.model != model:
        _provider = GroqProvider(api_key=api_key, model=model)
    return _provider
