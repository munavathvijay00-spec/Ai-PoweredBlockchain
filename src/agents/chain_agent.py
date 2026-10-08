"""
Chain Agent — specialized in blockchain-wide data.
"""
from loguru import logger
from src.agents.tools import get_tools


class ChainAgent:
    name = "chain_agent"
    role = "Analyzes blockchain-wide data (blocks, network activity)"

    async def handle(self, query: str, context: dict) -> dict:
        tools = get_tools()
        q = query.lower()
        try:
            block_num = await tools.get_latest_block_number()
            return {
                "agent": self.name,
                "answer": f"The latest Ethereum block is #{block_num:,}.",
                "data": {"latest_block": block_num},
            }
        except Exception as e:
            logger.exception(f"ChainAgent error: {e}")
            return {"agent": self.name, "answer": "Unable to fetch chain data.", "error": str(e)}


_agent = None


def get_chain_agent() -> ChainAgent:
    global _agent
    if _agent is None:
        _agent = ChainAgent()
    return _agent
