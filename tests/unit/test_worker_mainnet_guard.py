"""One-shot ingestion must refuse wrong-chain or failed RPC connections."""
import pytest
from unittest.mock import AsyncMock, patch
from src.ingest.worker import run_once


@pytest.mark.asyncio
async def test_run_once_fails_closed_before_database_access():
    with patch("src.ingest.worker.BlockchainClient") as client_class, patch(
        "src.ingest.worker.get_db", new_callable=AsyncMock
    ) as get_db:
        client = client_class.return_value
        client.connect = AsyncMock(return_value=False)
        client.close = AsyncMock()
        with pytest.raises(RuntimeError, match="mainnet"):
            await run_once()
        get_db.assert_not_awaited()
        client.close.assert_awaited_once()
