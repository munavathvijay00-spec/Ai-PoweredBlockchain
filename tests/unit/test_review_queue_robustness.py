"""Robust review queue contracts: clustering, evidence math, and audit writes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.analyst_routes import ReviewAction, _save_one
from src.api.auth import Principal
from src.api.browse_routes import _query_clusters


@pytest.mark.asyncio
async def test_cluster_query_collapses_sender_recipient_pairs_before_pagination():
    db = AsyncMock()
    db.fetch.return_value = []
    db.fetchval.return_value = 0
    repo = SimpleNamespace(db=db)

    await _query_clusters(repo, limit=25, offset=50, sort="risk_desc")

    sql = db.fetch.await_args.args[0]
    args = db.fetch.await_args.args[1:]
    assert "GROUP BY from_address_id, to_address_id" in sql
    assert "ROW_NUMBER() OVER" in sql
    assert "WHERE ranked.cluster_rank = 1" in sql
    assert "ARRAY_AGG(hash ORDER BY timestamp DESC, id DESC)" in sql
    assert "COUNT(DISTINCT block_number) AS cluster_blocks" in sql
    assert "COUNT(DISTINCT block_number) OVER" not in sql
    assert args[-2:] == (25, 50)


@pytest.mark.asyncio
async def test_cluster_total_counts_clusters_not_transactions():
    db = AsyncMock()
    db.fetch.return_value = []
    db.fetchval.return_value = 7
    repo = SimpleNamespace(db=db)

    _, total = await _query_clusters(repo, limit=10, offset=0)

    assert total == 7
    count_sql = db.fetchval.await_args.args[0]
    assert "GROUP BY t.from_address_id, t.to_address_id" in count_sql


@pytest.mark.asyncio
async def test_review_action_appends_authenticated_actor_and_state_transition():
    db = AsyncMock()
    db.fetchrow.side_effect = [
        {"status": "needs_review", "assignee": None, "note": "triage"},
        {
            "tx_hash": "0xabc", "status": "confirmed", "assignee": "fraud-team",
            "note": "evidence verified", "updated_at": None,
        },
    ]
    repo = SimpleNamespace(
        db=db,
        get_by_hash=AsyncMock(return_value={"hash": "0xabc"}),
    )
    action = ReviewAction(status="confirmed", assignee="fraud-team", note="evidence verified")
    principal = Principal(subject="analyst-team-a", role="analyst")

    result = await _save_one(repo, "0xabc", action, principal)

    assert result["status"] == "confirmed"
    assert result["actor"] == "analyst-team-a"
    assert result["actor_role"] == "analyst"
    audit_call = db.execute.await_args
    audit_sql = audit_call.args[0]
    assert "INSERT INTO transaction_review_audit" in audit_sql
    assert audit_call.args[1:] == (
        "0xabc", "analyst-team-a", "needs_review",
        "confirmed", "fraud-team", "evidence verified",
    )


def test_review_action_does_not_accept_client_actor_and_rejects_unknown_status():
    action = ReviewAction(status="confirmed", actor="spoofed-admin", note="test")
    assert not hasattr(action, "actor")
    with pytest.raises(Exception):
        ReviewAction(status="approved")
