"""Cloud agent API validation and authentication."""
from unittest.mock import patch, AsyncMock
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from src.api.agent_routes import router

app = FastAPI()
app.include_router(router)



@pytest.mark.asyncio
async def test_agent_catalog_public():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        result = await client.get("/api/agents")
    assert result.status_code == 200
    assert len(result.json()["agents"]) == 4


@pytest.mark.asyncio
async def test_analyze_requires_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post("/api/agents/analyze", json={"query": "latest block"})).status_code == 401


@pytest.mark.asyncio
async def test_invalid_address_rejected_with_key():
    with patch("src.api.agent_routes.get_settings") as settings:
        settings.return_value.api_key = "test-key"
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            result = await client.post("/api/agents/account", headers={"X-API-Key": "test-key"},
                             json={"address": "bad"})
    assert result.status_code == 422


@pytest.mark.asyncio
async def test_missing_transaction_hash_rejected():
    with patch("src.api.agent_routes.get_settings") as settings:
        settings.return_value.api_key = "test-key"
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            result = await client.post("/api/agents/transaction", headers={"X-API-Key": "test-key"}, json={})
    assert result.status_code == 422


@pytest.mark.asyncio
async def test_orchestrator_success():
    with patch("src.api.agent_routes.get_settings") as settings, patch("src.api.agent_routes.get_orchestrator") as orchestrator:
        settings.return_value.api_key = "test-key"
        orchestrator.return_value.run = AsyncMock(return_value={"agents_used": ["chain"], "answer": "ok"})
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            result = await client.post("/api/agents/analyze", headers={"X-API-Key": "test-key"},
                             json={"query": "latest Ethereum block"})
    assert result.status_code == 200
    assert result.json()["agents_used"] == ["chain"]
