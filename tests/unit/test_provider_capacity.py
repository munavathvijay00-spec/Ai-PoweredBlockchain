"""Regression tests for process-local wallet provider capacity protection."""

import asyncio

import pytest

from src.api.provider_capacity import ProviderCapacityExceeded, ProviderCapacityGuard


async def test_capacity_guard_limits_concurrent_requests():
    guard = ProviderCapacityGuard(max_concurrency=1, acquire_timeout_seconds=0.05)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with guard.slot():
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()

    assert guard.active == 1
    with pytest.raises(ProviderCapacityExceeded):
        async with guard.slot():
            pytest.fail("second request should not enter while capacity is exhausted")

    release.set()
    await task
    assert guard.active == 0


async def test_capacity_is_released_after_success():
    guard = ProviderCapacityGuard(max_concurrency=1, acquire_timeout_seconds=0.05)

    async with guard.slot():
        assert guard.active == 1

    assert guard.active == 0
    async with guard.slot():
        assert guard.active == 1

    assert guard.active == 0


async def test_capacity_is_released_after_exception():
    guard = ProviderCapacityGuard(max_concurrency=1, acquire_timeout_seconds=0.05)

    with pytest.raises(RuntimeError, match="boom"):
        async with guard.slot():
            assert guard.active == 1
            raise RuntimeError("boom")

    assert guard.active == 0
    async with guard.slot():
        assert guard.active == 1


async def test_capacity_is_released_after_cancellation():
    guard = ProviderCapacityGuard(max_concurrency=1, acquire_timeout_seconds=0.05)
    entered = asyncio.Event()

    async def cancellable():
        async with guard.slot():
            entered.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(cancellable())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert guard.active == 0
    async with guard.slot():
        assert guard.active == 1


@pytest.mark.parametrize(
    ("max_concurrency", "timeout"),
    [(0, 0.1), (-1, 0.1), (1, 0), (1, -0.1)],
)
def test_invalid_guard_configuration_fails_closed(max_concurrency, timeout):
    with pytest.raises(ValueError):
        ProviderCapacityGuard(max_concurrency, timeout)
