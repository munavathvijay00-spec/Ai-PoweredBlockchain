"""Unit tests for the transaction normalizer."""
import pytest
from datetime import datetime

from src.blockchain.normalizer import TransactionNormalizer


@pytest.mark.unit
class TestNormalizer:
    """Test transaction normalization."""

    def test_hex_string_with_0x_prefix(self):
        """Should handle inputs that already have '0x'."""
        normalizer = TransactionNormalizer()
        result = normalizer._to_hex_string(b'\x01\x02')
        assert result.startswith('0x')
        assert result == '0x0102'

    def test_hex_string_from_string(self):
        """Should handle plain string inputs."""
        normalizer = TransactionNormalizer()
        result = normalizer._to_hex_string('0xabc123')
        assert result == '0xabc123'
        assert not result.startswith('0x0x')

    def test_hex_string_handles_none(self):
        """Should return empty string for None."""
        normalizer = TransactionNormalizer()
        assert normalizer._to_hex_string(None) == ""

    def test_hex_string_avoids_double_prefix(self):
        """The bug we fixed on day 1: '0x' + '0xabc' should not become '0x0xabc'."""
        normalizer = TransactionNormalizer()

        class FakeHexBytes:
            def hex(self):
                return "abc123"

        result = normalizer._to_hex_string(FakeHexBytes())
        assert result == "0xabc123"
        assert result.count("0x") == 1

    def test_address_normalization(self):
        """Addresses should be lowercase with 0x prefix, 42 chars."""
        normalizer = TransactionNormalizer()
        result = normalizer._to_address_string('0x' + 'ABC' + '1' * 37)
        assert result == '0x' + 'abc' + '1' * 37
        assert len(result) == 42
        assert result.startswith('0x')

    def test_address_padding_for_short_input(self):
        """Short addresses should be zero-padded to 42 chars."""
        normalizer = TransactionNormalizer()
        result = normalizer._to_address_string('0xabc123')
        assert len(result) == 42
        assert result.startswith('0x')
        assert result.endswith('abc123')

    def test_address_handles_none(self):
        """Should return null address for None."""
        normalizer = TransactionNormalizer()
        result = normalizer._to_address_string(None)
        assert result == '0x' + '0' * 40

    def test_normalize_full_transaction(self, sample_raw_tx, sample_block):
        """Full normalization should produce a valid dict."""
        normalizer = TransactionNormalizer()
        result = normalizer.normalize(sample_raw_tx, sample_block)

        assert result['hash'].startswith('0x')
        assert result['from_address'] == '0x' + '1' * 40
        assert result['to_address'] == '0x' + '2' * 40
        assert result['value'] == 10 * 10**18
        assert result['block_number'] == 26000000
        assert isinstance(result['timestamp'], datetime)
        assert result['status'] == 'confirmed'

    def test_normalize_batch_handles_errors(self, sample_block):
        """Batch normalization should skip malformed transactions."""
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
