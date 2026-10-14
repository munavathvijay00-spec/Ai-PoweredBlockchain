"""Pattern intelligence agent for explainable retained-window behavioral motifs."""
from loguru import logger
from src.agents.tools import get_tools


class PatternAgent:
    name = "pattern_agent"
    role = "Detects explainable temporal and graph motifs such as burstiness, fan-in/out, reciprocal flow, and repeated amounts"

    async def handle(self, query: str, context: dict) -> dict:
        address = context.get("address")
        if not address:
            return {"agent": self.name, "answer": "I need an address for pattern analysis.", "error": "missing_address", "evidence": []}
        tools = get_tools()
        try:
            analysis = await tools.analyze_address_patterns(address)
            evidence = []
            for idx, signal in enumerate(analysis.get("signals") or [], start=1):
                stype = signal.get("type", "pattern")
                if stype == "bursty_activity":
                    claim = f"Observed {signal['observed']} retained transfers within a {signal['window_minutes']}-minute window."
                elif stype == "fan_out":
                    claim = f"Observed outgoing transfers to {signal['unique_outgoing_counterparties']} unique retained counterparties."
                elif stype == "fan_in":
                    claim = f"Observed incoming transfers from {signal['unique_incoming_counterparties']} unique retained counterparties."
                elif stype == "reciprocal_flow":
                    claim = f"Observed two-way retained flows with {len(signal.get('counterparties') or [])} counterparty address(es)."
                elif stype == "repeated_amounts":
                    claim = f"Observed {len(signal.get('amounts') or [])} transfer amount value(s) repeated at least three times."
                else:
                    claim = f"Observed pattern signal: {stype}."
                evidence.append({"id": f"P{idx}", "type": stype, "claim": claim, "source": "chainscope_retained_graph"})

            signal_names = [s.get("type") for s in analysis.get("signals") or []]
            if signal_names:
                answer = f"Retained-window pattern analysis observed: {', '.join(signal_names)}."
            else:
                answer = "No configured behavioral motif crossed its review threshold in the retained sample."
            answer += (
                f" Sample size: {analysis.get('sample_size', 0)} transactions; fan-in {analysis.get('fan_in', 0)}, "
                f"fan-out {analysis.get('fan_out', 0)}, peak 10-minute activity {analysis.get('max_transactions_in_10m', 0)}. "
                "Patterns are review indicators only and do not establish illicit intent."
            )
            return {
                "agent": self.name,
                "status": "ok",
                "answer": answer,
                "evidence": evidence,
                "data": analysis,
                "coverage": analysis.get("coverage_note"),
            }
        except Exception as exc:
            logger.exception(f"PatternAgent error: {exc}")
            return {"agent": self.name, "answer": "Unable to analyze patterns.", "error": str(exc), "evidence": []}


_agent = None


def get_pattern_agent() -> PatternAgent:
    global _agent
    if _agent is None:
        _agent = PatternAgent()
    return _agent
