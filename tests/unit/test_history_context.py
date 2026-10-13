import pytest
from datetime import datetime

from src.risk.history_context import load_recent_activity


class FakeDb:
    async def fetch(self, query, addresses, before_block, minutes):
        assert before_block == 100
        assert minutes == 30
        return [
            {
                "hash": "0x" + "1" * 64,
                "value": 5,
                "timestamp": datetime.utcnow(),
                "block_number": 99,
                "from_address": addresses[0],
                "to_address": addresses[1],
            }
        ]


@pytest.mark.asyncio
async def test_history_is_grouped_for_sender_and_recipient():
    a = "0x" + "a" * 40
    b = "0x" + "b" * 40
    result = await load_recent_activity(FakeDb(), [a, b], before_block=100)
    assert result[a][0]["direction"] == "outgoing"
    assert result[a][0]["counterparty"] == b
    assert result[b][0]["direction"] == "incoming"
    assert result[b][0]["counterparty"] == a
