"""Bounded contiguous block scheduling."""
import pytest
from src.ingest.loop import next_blocks


def test_starts_at_current_tip():
    assert next_blocks(None, 100) == [100]


def test_catches_up_without_gaps():
    assert next_blocks(100, 107) == [101, 102, 103]
    assert next_blocks(103, 107) == [104, 105, 106]
    assert next_blocks(106, 107) == [107]


def test_no_duplicate_at_stable_tip():
    assert next_blocks(100, 100) == []


def test_head_rollback_resets():
    assert next_blocks(105, 103) == [103]


def test_invalid_limit():
    with pytest.raises(ValueError):
        next_blocks(100, 101, 0)
