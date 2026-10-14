"""Wallet intelligence agent grounded in RPC state and retained investigation evidence."""
from loguru import logger
from src.agents.tools import get_tools


class AccountAgent:
    name = "account_agent"
    role = "Builds an evidence-backed wallet profile: balance, retained activity, counterparties, attribution, and risk context"

    async def handle(self, query: str, context: dict) -> dict:
        address = context.get("address")
        if not address:
            return {"agent": self.name, "answer": "I need an Ethereum address.", "error": "missing_address", "evidence": []}
        tools = get_tools()
        try:
            profile = await tools.get_address_profile(address)
            is_blacklisted = await tools.is_blacklisted(address)
            counterparties = await tools.find_counterparties(address, limit=5)
            first_seen = await tools.get_address_first_seen(address)

            evidence = [
                {"id": "W1", "type": "rpc_balance", "claim": f"Current balance is {profile['balance_eth']:.6f} ETH.", "source": "ethereum_rpc"},
                {"id": "W2", "type": "retained_activity", "claim": f"Retained data contains {profile['incoming_count']} incoming and {profile['outgoing_count']} outgoing transfers.", "source": "chainscope_db"},
                {"id": "W3", "type": "counterparty_scope", "claim": f"Retained data contains {profile['unique_counterparties']} unique counterparties.", "source": "chainscope_db"},
            ]
            if first_seen:
                evidence.append({"id": "W4", "type": "first_seen", "claim": f"Address first observed by ChainScope at {first_seen}.", "source": "chainscope_db"})
            if is_blacklisted:
                evidence.append({"id": "W5", "type": "manual_blacklist", "claim": "Address is present in the configured ChainScope blacklist.", "source": "chainscope_db"})
            if profile.get("entity_matches"):
                names = sorted({str(x.get("entity_name") or x.get("entity_id") or "attributed entity") for x in profile["entity_matches"]})
                evidence.append({"id": "W6", "type": "verified_entity_attribution", "claim": f"Exact-address attribution match: {', '.join(names[:3])}.", "source": "source_attributed_registry"})

            summary = (
                f"Wallet {address[:10]}… has {profile['balance_eth']:.4f} ETH currently; retained ChainScope data shows "
                f"{profile['incoming_count']} incoming, {profile['outgoing_count']} outgoing, and "
                f"{profile['unique_counterparties']} unique counterparties."
            )
            if counterparties:
                summary += f" Most frequent retained counterparties include {', '.join(counterparties[:3])}."
            summary += " These observations are bounded to ChainScope coverage and are not proof of wrongdoing."

            return {
                "agent": self.name,
                "status": "ok",
                "answer": summary,
                "evidence": evidence,
                "data": {**profile, "is_blacklisted": bool(is_blacklisted), "top_counterparties": counterparties},
                "coverage": profile.get("coverage_note"),
            }
        except Exception as exc:
            logger.exception(f"AccountAgent error: {exc}")
            return {"agent": self.name, "answer": "Unable to analyze address.", "error": str(exc), "evidence": []}


_agent = None


def get_account_agent() -> AccountAgent:
    global _agent
    if _agent is None:
        _agent = AccountAgent()
    return _agent
