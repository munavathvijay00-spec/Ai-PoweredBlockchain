"""Live-chain context agent with explicit evidence provenance."""
from loguru import logger
from src.agents.tools import get_tools


class ChainAgent:
    name = "chain_agent"
    role = "Provides live Ethereum chain context from RPC without inferring transaction intent"

    async def handle(self, query: str, context: dict) -> dict:
        tools = get_tools()
        try:
            block_num = await tools.get_latest_block_number()
            evidence = [{
                "id": "C1",
                "type": "latest_block",
                "claim": f"Ethereum RPC reports latest block #{block_num:,}.",
                "source": "ethereum_rpc",
            }]
            return {
                "agent": self.name,
                "status": "ok",
                "answer": f"Ethereum mainnet latest observed block is #{block_num:,}.",
                "evidence": evidence,
                "data": {"latest_block": block_num},
                "coverage": "Live chain context comes from the configured Ethereum RPC endpoint.",
            }
        except Exception as exc:
            logger.exception(f"ChainAgent error: {exc}")
            return {"agent": self.name, "answer": "Unable to fetch live chain data.", "error": str(exc), "evidence": []}


_agent = None


def get_chain_agent() -> ChainAgent:
    global _agent
    if _agent is None:
        _agent = ChainAgent()
    return _agent
