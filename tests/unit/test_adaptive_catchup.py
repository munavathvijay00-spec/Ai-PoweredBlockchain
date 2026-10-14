from src.ingest.loop import catchup_batch_size, catchup_sleep_seconds


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
