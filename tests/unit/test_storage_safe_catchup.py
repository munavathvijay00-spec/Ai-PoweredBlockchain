from src.ingest.loop import block_outside_live_retention


def test_block_older_than_live_window_is_header_only_candidate():
    now = 10_000
    assert block_outside_live_retention(
        {"timestamp": now - 31 * 60}, retention_minutes=30, now_ts=now
    ) is True


def test_recent_block_is_not_skipped():
    now = 10_000
    assert block_outside_live_retention(
        {"timestamp": now - 29 * 60}, retention_minutes=30, now_ts=now
    ) is False


def test_missing_or_invalid_timestamp_fails_safe_to_full_ingestion():
    assert block_outside_live_retention({}, retention_minutes=30, now_ts=10_000) is False
    assert block_outside_live_retention({"timestamp": "bad"}, retention_minutes=30, now_ts=10_000) is False
