"""
Pattern Agent — detects suspicious transaction patterns.
"""
from loguru import logger
from src.agents.tools import get_tools


class PatternAgent:
    name = "pattern_agent"
    role = "Detects suspicious patterns — bursty activity, ping-pong, clusters"

    async def handle(self, query: str, context: dict) -> dict:
        tools = get_tools()
        address = context.get("address")
        if not address:
            return {"agent": self.name, "answer": "I need an address for pattern analysis.", "error": "missing_address"}
        try:
            patterns = []
            is_bursty = await tools.detect_bursty_activity(address)
            if is_bursty:
                patterns.append("bursty_activity")

            counterparties = await tools.find_counterparties(address, limit=3)

            answer_parts = []
            if patterns:
                answer_parts.append(f"Detected patterns: {', '.join(patterns)}.")
            else:
                answer_parts.append("No suspicious patterns detected.")
            if counterparties:
                answer_parts.append(f"Interacts with {len(counterparties)} main counterparties.")

            return {
                "agent": self.name,
                "answer": " ".join(answer_parts),
                "data": {"address": address, "patterns": patterns},
            }
        except Exception as e:
            logger.exception(f"PatternAgent error: {e}")
            return {"agent": self.name, "answer": "Unable to analyze patterns.", "error": str(e)}


_agent = None


def get_pattern_agent() -> PatternAgent:
    global _agent
    if _agent is None:
        _agent = PatternAgent()
    return _agent
