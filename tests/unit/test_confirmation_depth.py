"""Regression tests for confirmed-only durable ingestion."""

import pytest

from src.ingest.loop import confirmed_head, next_blocks


def test_confirmed_head_excludes_volatile_tip():
    assert confirmed_head(1000, 12) == 988


def test_worker_schedule_never_crosses_confirmed_head():
    latest_rpc_head = 1000
    eligible = confirmed_head(latest_rpc_head, 12)
    scheduled = next_blocks(985, eligible, limit=20)
    assert scheduled == [986, 987, 988]
    assert max(scheduled) <= latest_rpc_head - 12


def test_confirmed_head_handles_early_chain_without_negative_height():
    assert confirmed_head(5, 12) == 0


@pytest.mark.parametrize("depth", [0, 65, -1])
def test_invalid_confirmation_depth_fails_closed(depth):
    with pytest.raises(ValueError):
        confirmed_head(1000, depth)


def test_negative_chain_head_is_rejected():
    with pytest.raises(ValueError):
        confirmed_head(-1, 12)
