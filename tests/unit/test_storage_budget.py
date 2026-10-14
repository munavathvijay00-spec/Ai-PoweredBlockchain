from src.storage_budget import (
    HISTORY_MAX_ROWS_GLOBAL,
    HISTORY_MAX_ROWS_PER_WALLET,
    LINEAGE_RETENTION_BLOCKS,
    LIVE_RETENTION_MINUTES,
    lineage_floor,
)
from src.ingest.loop import block_outside_live_retention


def test_free_tier_live_window_is_small_and_positive():
    assert LIVE_RETENTION_MINUTES == 5


def test_lineage_budget_exceeds_auto_reorg_depth_with_headroom():
    assert LINEAGE_RETENTION_BLOCKS >= 64
    assert lineage_floor(1_000) == 1_000 - LINEAGE_RETENTION_BLOCKS
    assert lineage_floor(10) == 0


def test_history_cache_is_bounded_but_useful():
    assert 1_000 <= HISTORY_MAX_ROWS_PER_WALLET <= HISTORY_MAX_ROWS_GLOBAL
    assert HISTORY_MAX_ROWS_GLOBAL <= 50_000


def test_default_retention_skips_definitely_stale_blocks():
    now = 10_000
    assert block_outside_live_retention({"timestamp": now - 6 * 60}, now_ts=now) is True
    assert block_outside_live_retention({"timestamp": now - 4 * 60}, now_ts=now) is False
