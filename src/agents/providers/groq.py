"""
Groq LLM provider — cloud-based, fast, free tier.
"""
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None


class GroqProvider:
    """Groq provider for LLM inference."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        if AsyncGroq is None:
            raise ImportError("groq package not installed. Run: pip install groq")
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        logger.info(f"🤖 Groq provider initialized (model={model})")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def generate(self, prompt: str, max_tokens: int = 250) -> str:
        """Generate text from a prompt."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise


_provider: Optional[GroqProvider] = None


def get_groq_provider(api_key: str) -> GroqProvider:
    global _provider
    if _provider is None:
        _provider = GroqProvider(api_key=api_key)
    return _provider
