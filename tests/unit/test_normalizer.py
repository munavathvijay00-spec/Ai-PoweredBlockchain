"""Unit tests for the transaction normalizer."""
import os
import time
from contextlib import contextmanager
from datetime import datetime

import pytest

from src.blockchain.normalizer import TransactionNormalizer


@contextmanager
def _temporary_timezone(name: str):
    """Temporarily change the process timezone when tzset is available."""
    if not hasattr(time, "tzset"):
        yield
        return
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


@pytest.mark.unit
class TestNormalizer:
    """Test transaction normalization."""

    def test_hex_string_with_0x_prefix(self):
        normalizer = TransactionNormalizer()
        result = normalizer._to_hex_string(b'\x01\x02')
        assert result.startswith('0x')
        assert result == '0x0102'

    def test_hex_string_from_string(self):
        normalizer = TransactionNormalizer()
        result = normalizer._to_hex_string('0xabc123')
        assert result == '0xabc123'
        assert not result.startswith('0x0x')

    def test_hex_string_handles_none(self):
        normalizer = TransactionNormalizer()
        assert normalizer._to_hex_string(None) == ""

    def test_hex_string_avoids_double_prefix(self):
        normalizer = TransactionNormalizer()

        class FakeHexBytes:
            def hex(self):
                return "abc123"

        result = normalizer._to_hex_string(FakeHexBytes())
        assert result == "0xabc123"
        assert result.count("0x") == 1

    def test_address_normalization(self):
        normalizer = TransactionNormalizer()
        result = normalizer._to_address_string('0x' + 'ABC' + '1' * 37)
        assert result == '0x' + 'abc' + '1' * 37
        assert len(result) == 42
        assert result.startswith('0x')

    def test_short_address_is_rejected(self):
        normalizer = TransactionNormalizer()
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            normalizer._to_address_string('0xabc123')

    def test_address_handles_none(self):
        normalizer = TransactionNormalizer()
        result = normalizer._to_address_string(None)
        assert result == '0x' + '0' * 40

    def test_utc_timestamp_is_independent_of_host_timezone(self):
        normalizer = TransactionNormalizer()
        unix_seconds = 1_700_000_000

        with _temporary_timezone("UTC"):
            utc_result = normalizer._utc_naive_timestamp(unix_seconds)
        with _temporary_timezone("Asia/Kolkata"):
            kolkata_result = normalizer._utc_naive_timestamp(unix_seconds)

        assert utc_result == datetime(2023, 11, 14, 22, 13, 20)
        assert kolkata_result == utc_result
        assert utc_result.tzinfo is None

    @pytest.mark.parametrize("bad_value", [None, "not-a-timestamp", -1])
    def test_invalid_block_timestamp_is_rejected(self, bad_value):
        normalizer = TransactionNormalizer()
        with pytest.raises(ValueError, match="Invalid block timestamp"):
            normalizer._utc_naive_timestamp(bad_value)

    def test_normalize_full_transaction(self, sample_raw_tx, sample_block):
        normalizer = TransactionNormalizer()
        result = normalizer.normalize(sample_raw_tx, sample_block)

        assert result['hash'].startswith('0x')
        assert result['from_address'] == '0x' + '1' * 40
        assert result['to_address'] == '0x' + '2' * 40
        assert result['value'] == 10 * 10**18
        assert result['block_number'] == 26000000
        assert isinstance(result['timestamp'], datetime)
        assert result['timestamp'].tzinfo is None
        assert result['status'] == 'confirmed'

    def test_normalize_batch_handles_errors(self, sample_block):
        normalizer = TransactionNormalizer()

        good_tx = {
            'hash': bytes.fromhex('a' * 64),
            'from': '0x' + '1' * 40,
            'to': '0x' + '2' * 40,
            'value': 100,
            'gasPrice': 1000,
            'gas': 21000,
        }
        bad_tx = {'hash': None, 'from': None}

        results = normalizer.normalize_batch([good_tx, bad_tx], sample_block)
        assert len(results) >= 1
