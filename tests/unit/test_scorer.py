"""Unit tests for the risk scorer."""
import pytest

from src.risk.scorer import RiskScorer


@pytest.mark.unit
class TestRiskScorer:
    """Test risk scoring heuristics."""

    def setup_method(self):
        """Create a fresh scorer for each test."""
        self.scorer = RiskScorer(
            large_tx_threshold_eth=10.0,
            bursty_window_minutes=60,
            bursty_threshold=10,
            new_wallet_days=30,
        )

    async def test_blacklisted_address_returns_100(self, sample_tx):
        """Any blacklisted interaction = instant 100."""
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=True,
        )
        assert result['score'] == 100
        assert any('blacklist' in f['factor'] for f in result['factors'])

    async def test_large_transaction_adds_20(self, sample_tx):
        """Large tx value adds 20 points."""
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=False,
        )
        # sample_tx has 10 ETH, threshold is 10 → not strictly greater
        # Change to make it clearly large
        sample_tx['value'] = 100 * 10**18
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=False,
        )
        assert result['score'] >= 20
        assert any('large_transaction' in f['factor'] for f in result['factors'])

    async def test_zero_value_adds_5(self, sample_tx):
        """Zero-value tx (contract call) adds 5 points."""
        sample_tx['value'] = 0
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=False,
        )
        assert result['score'] >= 5
        assert any('zero_value' in f['factor'] for f in result['factors'])

    async def test_clean_transaction_low_score(self, sample_tx):
        """A small, normal transaction should have a low score."""
        sample_tx['value'] = 1 * 10**18  # 1 ETH
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=False,
        )
        assert result['score'] < 15  # should be low

    async def test_score_capped_at_100(self, sample_tx):
        """Score must never exceed 100."""
        sample_tx['value'] = 10**21  # 1000 ETH
        # Add fake history to trigger more factors
        history = [
            {'to_address': '0x' + 'x' * 40, 'value': 100, 'timestamp': None}
            for _ in range(20)
        ]
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=history,
            is_blacklisted=True,
        )
        assert result['score'] == 100
        assert result['score'] <= 100

    async def test_returns_factors_list(self, sample_tx):
        """Result should include a factors list."""
        result = await self.scorer.score_transaction(
            tx=sample_tx,
            address_history=[],
            is_blacklisted=False,
        )
        assert 'score' in result
        assert 'factors' in result
        assert isinstance(result['factors'], list)

    def test_detect_bursty_with_history(self):
        """Should detect bursty activity with many recent txs."""
        from datetime import datetime
        now = datetime.now()
        history = [
            {'to_address': '0x' + 'x' * 40, 'value': 100, 'timestamp': now}
            for _ in range(15)
        ]
        assert self.scorer._detect_bursty(history) is True

    def test_detect_bursty_with_empty_history(self):
        """Empty history = no bursty."""
        assert self.scorer._detect_bursty([]) is False

    def test_detect_ping_pong_pattern(self):
        """Detects back-and-forth between same addresses."""
        history = [
            {'to_address': '0x' + 'a' * 40},
            {'to_address': '0x' + 'b' * 40},
            {'to_address': '0x' + 'a' * 40},
            {'to_address': '0x' + 'b' * 40},
            {'to_address': '0x' + 'a' * 40},
            {'to_address': '0x' + 'b' * 40},
        ]
        assert self.scorer._detect_ping_pong(history) is True

    def test_no_ping_pong_pattern(self):
        """Diverse addresses = no ping-pong."""
        history = [
            {'to_address': f'0x{i:040x}'}
            for i in range(10)
        ]
        assert self.scorer._detect_ping_pong(history) is False