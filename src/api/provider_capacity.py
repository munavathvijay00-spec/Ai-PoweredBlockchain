"""Per-process capacity protection for provider-backed wallet investigations.

This is deliberately not described as distributed rate limiting. It bounds the
number of concurrent wallet-investigation requests handled by one API process so
provider quota and sockets are not exhausted by an unbounded burst.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException

from src.utils.config import get_settings


class ProviderCapacityExceeded(RuntimeError):
    """Raised when a request cannot obtain provider capacity quickly enough."""


class ProviderCapacityGuard:
    """Bound concurrent provider-backed requests within one API process."""

    def __init__(self, max_concurrency: int, acquire_timeout_seconds: float):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if acquire_timeout_seconds <= 0:
            raise ValueError("acquire_timeout_seconds must be positive")
        self.max_concurrency = int(max_concurrency)
        self.acquire_timeout_seconds = float(acquire_timeout_seconds)
        self._semaphore = asyncio.BoundedSemaphore(self.max_concurrency)
        self._active = 0
        self._state_lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    @asynccontextmanager
    async def slot(self):
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.acquire_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderCapacityExceeded(
                "provider-backed wallet investigation capacity exhausted"
            ) from exc

        async with self._state_lock:
            self._active += 1
        try:
            yield
        finally:
            async with self._state_lock:
                self._active -= 1
            self._semaphore.release()


_guard: ProviderCapacityGuard | None = None
_guard_config: tuple[int, float] | None = None


def get_provider_capacity_guard() -> ProviderCapacityGuard:
    """Return the process-local guard configured from validated settings."""
    global _guard, _guard_config
    settings = get_settings()
    config = (
        settings.wallet_provider_max_concurrent_requests,
        settings.wallet_provider_acquire_timeout_seconds,
    )
    if _guard is None or _guard_config != config:
        _guard = ProviderCapacityGuard(*config)
        _guard_config = config
    return _guard


async def require_provider_capacity():
    """FastAPI dependency that sheds excess load before calling the provider."""
    guard = get_provider_capacity_guard()
    try:
        async with guard.slot():
            yield
    except ProviderCapacityExceeded as exc:
        raise HTTPException(
            status_code=503,
            detail="Wallet investigation capacity is temporarily exhausted; retry shortly",
            headers={"Retry-After": "1"},
        ) from exc
