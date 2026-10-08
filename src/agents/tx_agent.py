"""
Transaction Agent — specialized in individual transaction analysis.
"""
from loguru import logger
from src.agents.tools import get_tools


class TransactionAgent:
    name = "tx_agent"
    role = "Analyzes individual transactions — risk, value, purpose"

    async def handle(self, query: str, context: dict) -> dict:
        tools = get_tools()
        tx_hash = context.get("tx_hash")
        if not tx_hash:
            return {"agent": self.name, "answer": "I need a transaction hash.", "error": "missing_tx_hash"}
        try:
            tx = await tools.get_transaction_by_hash(tx_hash)
            if not tx:
                return {"agent": self.name, "answer": f"Transaction not found.", "error": "not_found"}

            value_eth = tx.get('value', 0) / 10**18
            risk = tx.get('risk_score', 0)

            parts = [
                f"Transaction {tx_hash[:16]}...",
                f"moved {value_eth:.4f} ETH",
                f"in block #{tx.get('block_number', 0):,}.",
                f"Risk score: {risk}/100.",
            ]
            if tx.get('ai_explanation'):
                parts.append(f"Previous analysis: {tx['ai_explanation']}")

            return {
                "agent": self.name,
                "answer": " ".join(parts),
                "data": {"tx_hash": tx_hash, "value_eth": value_eth, "risk_score": risk},
            }
        except Exception as e:
            logger.exception(f"TransactionAgent error: {e}")
            return {"agent": self.name, "answer": "Unable to analyze transaction.", "error": str(e)}


_agent = None


def get_transaction_agent() -> TransactionAgent:
    global _agent
    if _agent is None:
        _agent = TransactionAgent()
    return _agent
