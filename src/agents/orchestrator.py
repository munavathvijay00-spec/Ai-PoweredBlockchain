"""Evidence-led orchestrator for ChainScope specialist agents.

The orchestrator routes by explicit entity/query intent, runs independent specialists in
parallel, namespaces their evidence, and allows an optional LLM analyst to synthesize only
those evidence items. Invalid model output fails closed to deterministic synthesis.
"""
import asyncio
import re
from typing import Dict, List, Optional
from loguru import logger

from src.agents.chain_agent import get_chain_agent
from src.agents.account_agent import get_account_agent
from src.agents.tx_agent import get_transaction_agent
from src.agents.pattern_agent import get_pattern_agent
from src.agents.investigation_analyst import synthesize_agent_evidence


class Orchestrator:
    ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
    TX_HASH_RE = re.compile(r"0x[a-fA-F0-9]{64}")

    CHAIN_KEYWORDS = ("block", "network", "latest", "chain", "gas", "mainnet")
    ACCOUNT_KEYWORDS = ("address", "wallet", "account", "balance", "counterparty")
    TX_KEYWORDS = ("transaction", "tx", "hash", "transfer", "risk", "explain")
    PATTERN_KEYWORDS = ("pattern", "suspicious", "bursty", "unusual", "behavior", "flow", "fan-in", "fan-out", "reciprocal")

    def _extract_entities(self, query: str) -> Dict:
        entities: Dict[str, str] = {}
        tx_match = self.TX_HASH_RE.search(query)
        if tx_match:
            entities["tx_hash"] = tx_match.group(0)
        remainder = self.TX_HASH_RE.sub("", query)
        addr_match = self.ADDRESS_RE.search(remainder)
        if addr_match:
            entities["address"] = addr_match.group(0)
        return entities

    def _select_agents(self, query: str, entities: Dict) -> List[str]:
        q = query.lower()
        agents: List[str] = []
        if "tx_hash" in entities:
            agents.append("transaction")
        if "address" in entities:
            agents.extend(["account", "pattern"])
        if any(k in q for k in self.CHAIN_KEYWORDS):
            agents.append("chain")
        if any(k in q for k in self.ACCOUNT_KEYWORDS) and "address" in entities:
            agents.append("account")
        if any(k in q for k in self.TX_KEYWORDS) and "tx_hash" in entities:
            agents.append("transaction")
        if any(k in q for k in self.PATTERN_KEYWORDS) and "address" in entities:
            agents.append("pattern")
        if not agents:
            agents.append("chain")
        return list(dict.fromkeys(agents))

    async def _run_one(self, name: str, agent, query: str, context: Dict) -> Dict:
        try:
            return await asyncio.wait_for(agent.handle(query, context), timeout=20)
        except asyncio.TimeoutError:
            return {"agent": name, "answer": f"{name} timed out.", "error": "timeout", "evidence": []}
        except Exception as exc:
            logger.exception(f"{name} failed: {exc}")
            return {"agent": name, "answer": f"{name} failed safely.", "error": str(exc), "evidence": []}

    @staticmethod
    def _evidence_ledger(results: List[Dict]) -> List[Dict]:
        ledger: List[Dict] = []
        seen = set()
        for result in results:
            agent = str(result.get("agent") or "agent")
            for item in result.get("evidence") or []:
                claim = str(item.get("claim") or "").strip()
                if not claim:
                    continue
                key = (agent, claim)
                if key in seen:
                    continue
                seen.add(key)
                entry = dict(item)
                entry["agent"] = agent
                entry["id"] = f"{agent}:{item.get('id') or len(ledger)+1}"
                ledger.append(entry)
        return ledger

    @staticmethod
    def _deterministic_synthesis(results: List[Dict], ledger: List[Dict]) -> str:
        successful = [r for r in results if not r.get("error")]
        if not successful:
            return "No specialist completed successfully; no investigation conclusion was produced."
        pieces = [str(r.get("answer") or "").strip() for r in successful if str(r.get("answer") or "").strip()]
        summary = " ".join(pieces)
        if ledger:
            summary += f" The investigation ledger contains {len(ledger)} explicit evidence item(s)."
        summary += " Review indicators and graph motifs are contextual evidence, not proof of wrongdoing."
        return summary

    async def run(self, query: str) -> Dict:
        logger.info(f"Orchestrator investigation: {query[:100]}")
        entities = self._extract_entities(query)
        agent_names = self._select_agents(query, entities)
        context = dict(entities)
        agent_map = {
            "chain": get_chain_agent(),
            "account": get_account_agent(),
            "transaction": get_transaction_agent(),
            "pattern": get_pattern_agent(),
        }
        results = list(await asyncio.gather(*[
            self._run_one(name, agent_map[name], query, context) for name in agent_names
        ]))
        ledger = self._evidence_ledger(results)
        deterministic = self._deterministic_synthesis(results, ledger)
        analyst = await synthesize_agent_evidence(ledger)
        answer = analyst.get("text") if analyst.get("status") == "grounded_ai" and analyst.get("grounded") else deterministic

        failures = [r for r in results if r.get("error")]
        successful = len(results) - len(failures)
        return {
            "query": query,
            "entities": entities,
            "agents_used": agent_names,
            "answer": answer,
            "synthesis": {
                "mode": "grounded_ai" if analyst.get("status") == "grounded_ai" and analyst.get("grounded") else "deterministic_fallback",
                "analyst": analyst,
            },
            "evidence_ledger": ledger,
            "agent_results": results,
            "investigation_quality": {
                "agents_requested": len(agent_names),
                "agents_successful": successful,
                "agents_failed": len(failures),
                "evidence_items": len(ledger),
                "complete": successful == len(agent_names),
                "grounding_mode": "validated multi-agent evidence ledger",
            },
            "limitations": [
                "ChainScope transaction/history observations are bounded to available retained or indexed coverage.",
                "Behavioral patterns are review signals and do not establish identity, intent, or illegality.",
                "LLM synthesis is accepted only when every factual claim validates against specialist evidence.",
            ],
        }


_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
