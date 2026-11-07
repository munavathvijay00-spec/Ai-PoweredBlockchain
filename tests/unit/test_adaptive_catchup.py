from src.ingest.loop import catchup_batch_size, catchup_sleep_seconds, ingestion_retry_delay


def test_batch_size_grows_only_when_materially_behind():
    assert catchup_batch_size(0) == 3
    assert catchup_batch_size(20) == 3
    assert catchup_batch_size(21) == 6
    assert catchup_batch_size(100) == 6
    assert catchup_batch_size(101) == 12
    assert catchup_batch_size(1000) == 12


def test_sleep_shortens_during_catchup_but_respects_requested_interval():
    assert catchup_sleep_seconds(0, 15) == 15
    assert catchup_sleep_seconds(21, 15) == 5
    assert catchup_sleep_seconds(101, 15) == 2
    assert catchup_sleep_seconds(101, 1) == 1


def test_retry_backoff_is_bounded_and_resets_after_success():
    assert [ingestion_retry_delay(n, 15) for n in range(1, 6)] == [15, 30, 60, 120, 120]
    assert ingestion_retry_delay(20, 15) == 120
