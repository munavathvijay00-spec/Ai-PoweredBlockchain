"""
Account Agent — specialized in wallet analysis.
"""
from loguru import logger
from src.agents.tools import get_tools


class AccountAgent:
    name = "account_agent"
    role = "Analyzes wallet addresses — age, balance, activity, reputation"

    async def handle(self, query: str, context: dict) -> dict:
        tools = get_tools()
        address = context.get("address")
        if not address:
            return {"agent": self.name, "answer": "I need an Ethereum address.", "error": "missing_address"}
        try:
            is_black = await tools.is_blacklisted(address)
            tx_count = await tools.get_transaction_count(address)
            first_seen = await tools.get_address_first_seen(address)
            counterparties = await tools.find_counterparties(address, limit=5)

            findings = []
            if is_black:
                findings.append("⚠️ This address is on the blacklist.")
            if tx_count > 0:
                findings.append(f"Has been involved in {tx_count:,} transactions.")
            if first_seen:
                findings.append(f"First seen: {first_seen}.")
            if counterparties:
                findings.append(f"Top counterparties: {', '.join(counterparties[:3])}.")

            return {
                "agent": self.name,
                "answer": " ".join(findings) if findings else "No data available.",
                "data": {"address": address, "is_blacklisted": is_black, "transaction_count": tx_count},
            }
        except Exception as e:
            logger.exception(f"AccountAgent error: {e}")
            return {"agent": self.name, "answer": "Unable to analyze address.", "error": str(e)}


_agent = None


def get_account_agent() -> AccountAgent:
    global _agent
    if _agent is None:
        _agent = AccountAgent()
    return _agent
