"""Cloud-facing read-only multi-agent intelligence endpoints."""
import asyncio
import hmac
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from src.agents.orchestrator import get_orchestrator
from src.agents.chain_agent import get_chain_agent
from src.agents.account_agent import get_account_agent
from src.agents.tx_agent import get_transaction_agent
from src.agents.pattern_agent import get_pattern_agent
from src.utils.config import get_settings

router = APIRouter(prefix="/api/agents", tags=["multi-agent intelligence"])
ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
TX_HASH = re.compile(r"^0x[a-fA-F0-9]{64}$")
AGENTS = {
    "chain": get_chain_agent,
    "account": get_account_agent,
    "transaction": get_transaction_agent,
    "pattern": get_pattern_agent,
}


async def require_agent_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


class AnalysisRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)


class AgentRequest(BaseModel):
    query: str = Field(default="Investigate this Ethereum entity", max_length=500)
    address: str | None = None
    tx_hash: str | None = None


@router.get("")
async def list_agents():
    return {"agents": [{"name": name, "role": factory().role} for name, factory in AGENTS.items()],
            "orchestrator": "/api/agents/analyze", "authentication": "X-API-Key header required for analysis"}


@router.post("/analyze", dependencies=[Depends(require_agent_key)])
async def analyze(request: AnalysisRequest):
    try:
        return await asyncio.wait_for(get_orchestrator().run(request.query), timeout=25)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent analysis timed out")


@router.post("/{agent_name}", dependencies=[Depends(require_agent_key)])
async def run_agent(agent_name: Literal["chain", "account", "transaction", "pattern"], request: AgentRequest):
    if request.address is not None and not ADDRESS.fullmatch(request.address):
        raise HTTPException(status_code=422, detail="Invalid Ethereum wallet address")
    if request.tx_hash is not None and not TX_HASH.fullmatch(request.tx_hash):
        raise HTTPException(status_code=422, detail="Invalid Ethereum transaction hash")
    if agent_name in ("account", "pattern") and not request.address:
        raise HTTPException(status_code=422, detail="address is required")
    if agent_name == "transaction" and not request.tx_hash:
        raise HTTPException(status_code=422, detail="tx_hash is required")
    context = {key: value for key, value in {"address": request.address, "tx_hash": request.tx_hash}.items() if value}
    try:
        result = await asyncio.wait_for(AGENTS[agent_name]().handle(request.query, context), timeout=25)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent analysis timed out")
    return {"agent": agent_name, "result": result}
