"""Unit tests for Pydantic models."""
import pytest
from datetime import datetime

from src.api.models import (
    TransactionResponse,
    TransactionListResponse,
    StatsResponse,
    HealthResponse,
)


@pytest.mark.unit
class TestModels:
    """Test response model validation."""

    def test_transaction_response_valid(self):
        """Valid tx response."""
        tx = TransactionResponse(
            hash='0x' + 'a' * 64,
            from_address='0x' + '1' * 40,
            to_address='0x' + '2' * 40,
            value_wei='1000000000000000000',
            value_eth=1.0,
            block_number=26000000,
            timestamp=datetime.now(),
            risk_score=50,
            ai_explanation=None,
        )
        assert tx.risk_score == 50
        assert tx.value_eth == 1.0

    def test_risk_score_must_be_0_to_100(self):
        """Risk score validated to 0-100."""
        with pytest.raises(Exception):  # ValidationError
            TransactionResponse(
                hash='0x' + 'a' * 64,
                from_address='0x' + '1' * 40,
                to_address='0x' + '2' * 40,
                value_wei='0',
                value_eth=0.0,
                block_number=1,
                timestamp=datetime.now(),
                risk_score=150,  # invalid
                ai_explanation=None,
            )

    def test_stats_response_valid(self):
        """Valid stats."""
        stats = StatsResponse(
            total_transactions=100,
            total_addresses=50,
            flagged_transactions=5,
            avg_risk_score=3.5,
            max_risk_score=80,
            explained_transactions=4,
        )
        assert stats.total_transactions == 100

    def test_health_response_valid(self):
        """Health check response."""
        health = HealthResponse(
            status='operational',
            service='Blockchain Intelligence Platform',
            version='1.0.0',
            database='blockchain_analytics',
            blockchain='ethereum-mainnet',
        )
        assert health.status == 'operational'