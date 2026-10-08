"""
Orchestrator — coordinates multiple specialized agents.
"""
import re
from typing import Dict, List, Optional
from loguru import logger

from src.agents.chain_agent import get_chain_agent
from src.agents.account_agent import get_account_agent
from src.agents.tx_agent import get_transaction_agent
from src.agents.pattern_agent import get_pattern_agent


class Orchestrator:
    ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
    TX_HASH_RE = re.compile(r"0x[a-fA-F0-9]{64}")

    CHAIN_KEYWORDS = ["block", "network", "latest", "chain", "gas"]
    ACCOUNT_KEYWORDS = ["address", "wallet", "account", "balance"]
    TX_KEYWORDS = ["transaction", "tx", "hash", "transfer"]
    PATTERN_KEYWORDS = ["pattern", "suspicious", "bursty", "unusual", "behavior"]

    def _extract_entities(self, query: str) -> Dict:
        entities = {}
        tx_match = self.TX_HASH_RE.search(query)
        if tx_match:
            entities["tx_hash"] = tx_match.group(0)
            return entities
        addr_match = self.ADDRESS_RE.search(query)
        if addr_match:
            entities["address"] = addr_match.group(0)
        return entities

    def _select_agents(self, query: str, entities: Dict) -> List[str]:
        q = query.lower()
        agents = []

        if "tx_hash" in entities:
            agents.append("transaction")
        elif "address" in entities:
            agents.append("account")
            agents.append("pattern")

        if any(k in q for k in self.CHAIN_KEYWORDS) and "chain" not in agents:
            agents.append("chain")
        if any(k in q for k in self.PATTERN_KEYWORDS) and "pattern" not in agents:
            agents.append("pattern")

        if not agents:
            agents.append("chain")

        return agents

    async def run(self, query: str) -> Dict:
        logger.info(f"🎯 Orchestrator: {query[:80]}")
        entities = self._extract_entities(query)
        agent_names = self._select_agents(query, entities)
        context = dict(entities)

        agent_map = {
            "chain": get_chain_agent(),
            "account": get_account_agent(),
            "transaction": get_transaction_agent(),
            "pattern": get_pattern_agent(),
        }

        results = []
        for name in agent_names:
            agent = agent_map.get(name)
            if not agent:
                continue
            try:
                result = await agent.handle(query, context)
                results.append(result)
            except Exception as e:
                logger.exception(f"❌ {name} failed: {e}")
                results.append({"agent": name, "answer": f"Failed: {e}", "error": str(e)})

        combined = " ".join(r.get("answer", "") for r in results if r.get("answer"))

        return {
            "query": query,
            "entities": entities,
            "agents_used": agent_names,
            "answer": combined,
            "agent_results": results,
        }


_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
