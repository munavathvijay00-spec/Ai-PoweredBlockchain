"""Transaction intelligence agent grounded in stored facts, risk evidence, and nearby activity."""
import json
from loguru import logger
from src.agents.tools import get_tools


def _factors(value):
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


class TransactionAgent:
    name = "tx_agent"
    role = "Investigates one transaction using transfer facts, detector evidence, entity attribution, and nearby retained activity"

    async def handle(self, query: str, context: dict) -> dict:
        tx_hash = context.get("tx_hash")
        if not tx_hash:
            return {"agent": self.name, "answer": "I need a transaction hash.", "error": "missing_tx_hash", "evidence": []}
        tools = get_tools()
        try:
            result = await tools.get_transaction_context(tx_hash)
            if not result:
                return {"agent": self.name, "answer": "Transaction not found in retained ChainScope data.", "error": "not_found", "evidence": []}
            tx = result["transaction"]
            value_wei = int(tx.get("value") or 0)
            value_eth = value_wei / 10**18
            risk = int(tx.get("risk_score") or 0)
            evidence = [
                {"id": "T1", "type": "transfer_fact", "claim": f"Transaction moved {value_eth:.8f} ETH in block {int(tx.get('block_number') or 0)}.", "source": "chainscope_db"},
                {"id": "T2", "type": "risk_score", "claim": f"Stored review risk score is {risk}/100.", "source": "chainscope_detector"},
            ]
            factors = _factors(tx.get("risk_factors"))
            for idx, factor in enumerate(factors[:4], start=3):
                reason = str(factor.get("reason") or factor.get("type") or "detector signal")
                points = factor.get("points")
                suffix = f" (+{points} points)" if points is not None else ""
                evidence.append({"id": f"T{idx}", "type": "detector_evidence", "claim": f"{reason}{suffix}.", "source": "chainscope_detector"})
            entity_matches = result.get("entity_matches") or {}
            names = []
            for items in entity_matches.values():
                for item in items:
                    names.append(str(item.get("entity_name") or item.get("entity_id") or "attributed entity"))
            if names:
                evidence.append({"id": f"T{len(evidence)+1}", "type": "entity_attribution", "claim": f"Exact-address attribution matched {', '.join(sorted(set(names))[:3])}.", "source": "source_attributed_registry"})

            nearby = result.get("nearby_activity") or []
            answer = (
                f"Transaction {tx_hash[:14]}… moved {value_eth:.6f} ETH in block {int(tx.get('block_number') or 0):,}. "
                f"Its stored review score is {risk}/100 with {len(factors)} detector evidence item(s). "
                f"ChainScope found {len(nearby)} nearby retained transaction(s) involving the sender or receiver. "
                "This is investigative context, not a fraud verdict."
            )
            return {
                "agent": self.name,
                "status": "ok",
                "answer": answer,
                "evidence": evidence,
                "data": {
                    "tx_hash": tx_hash,
                    "value_eth": value_eth,
                    "risk_score": risk,
                    "risk_factors": factors,
                    "entity_matches": entity_matches,
                    "nearby_activity": nearby,
                },
                "coverage": "Transaction and nearby activity are bounded to retained ChainScope data.",
            }
        except Exception as exc:
            logger.exception(f"TransactionAgent error: {exc}")
            return {"agent": self.name, "answer": "Unable to analyze transaction.", "error": str(exc), "evidence": []}


_agent = None


def get_transaction_agent() -> TransactionAgent:
    global _agent
    if _agent is None:
        _agent = TransactionAgent()
    return _agent
