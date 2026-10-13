"""Dashboard counters, filters, and thresholds must share one contract."""
from unittest.mock import AsyncMock

import pytest

from src.api.routes import (
    CRITICAL_THRESHOLD,
    FLAGGED_THRESHOLD,
    HIGH_RISK_THRESHOLD,
    get_stats,
    list_flagged,
)


@pytest.mark.asyncio
async def test_stats_exposes_exact_thresholds_used_by_sql():
    tx_repo = AsyncMock()
    addr_repo = AsyncMock()
    tx_repo.count.return_value = 100
    addr_repo.count.return_value = 60
    tx_repo.db.fetchrow.return_value = {
        "avg_score": 7.25,
        "max_score": 85,
        "flagged": 12,
        "high_risk": 5,
        "critical": 1,
        "explained": 10,
        "grounded_explanations": 8,
    }

    result = await get_stats(tx_repo=tx_repo, addr_repo=addr_repo)

    assert result.flagged_transactions == 12
    assert result.flagged_threshold == FLAGGED_THRESHOLD == 20
    assert result.high_risk_transactions == 5
    assert result.high_risk_threshold == HIGH_RISK_THRESHOLD == 40
    assert result.critical_transactions == 1
    assert result.critical_threshold == CRITICAL_THRESHOLD == 80
    assert result.grounded_explanations == 8

    sql, flagged, high, critical = tx_repo.db.fetchrow.await_args.args
    assert "risk_score >= $1" in sql
    assert (flagged, high, critical) == (20, 40, 80)


@pytest.mark.asyncio
async def test_flagged_page_total_uses_same_requested_threshold():
    repo = AsyncMock()
    repo.list_flagged.return_value = []
    repo.count_flagged.return_value = 196

    result = await list_flagged(min_score=FLAGGED_THRESHOLD, limit=50, repo=repo)

    assert result.total == 196
    repo.list_flagged.assert_awaited_once_with(min_score=20, limit=50)
    repo.count_flagged.assert_awaited_once_with(min_score=20)
