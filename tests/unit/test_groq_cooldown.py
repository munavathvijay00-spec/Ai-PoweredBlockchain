"""Rate-limit behavior: no retries or requests during provider cooldown."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.providers import groq as module


@pytest.mark.asyncio
async def test_cooldown_skips_provider_calls():
    provider = object.__new__(module.GroqProvider)
    provider.model = "test"
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock()
    import asyncio
    import time
    provider._request_lock = asyncio.Lock()
    provider._cooldown_until = time.monotonic() + 60
    assert await provider.generate("test") == ""
    provider.client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_generation():
    provider = object.__new__(module.GroqProvider)
    provider.model = "test"
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Clear evidence"))])
    )
    import asyncio
    provider._request_lock = asyncio.Lock()
    provider._cooldown_until = 0
    assert await provider.generate("test") == "Clear evidence"
    provider.client.chat.completions.create.assert_awaited_once()
