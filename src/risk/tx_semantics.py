"""Conservative, evidence-linked transaction semantic candidates.

Never infer a swap or bridge merely from a token transfer. Output differentiates
contract-call selector, labeled destination, and observed transfer evidence.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

# Only canonical, independently recognizable ABI function selectors.
KNOWN_SELECTORS = {
    "0xa9059cbb": "erc20_transfer",
    "0x095ea7b3": "erc20_approval",
    "0x38ed1739": "uniswap_v2_swap_exact_tokens_for_tokens",
    "0x7ff36ab5": "uniswap_v2_swap_exact_eth_for_tokens",
    "0x18cbafe5": "uniswap_v2_swap_exact_tokens_for_eth",
    "0x414bf389": "uniswap_v3_exact_input_single",
    "0x3593564c": "uniswap_universal_router_execute",
}

def selector_candidate(input_data: str | None) -> dict:
    selector = str(input_data or "")[:10].lower()
    if selector not in KNOWN_SELECTORS:
        return {"semantic": "unknown_contract_call", "evidence_level": "none", "selector": selector or None}
    return {
        "semantic": KNOWN_SELECTORS[selector],
        "evidence_level": "method_selector_only",
        "selector": selector,
        "caution": "Method selector alone does not prove successful execution or resulting asset flow.",
    }


def summarize_transfer_semantics(native_edges: list[dict], token_edges: list[dict]) -> list[dict]:
    """Analyze shared tx hashes, without fabricating swap/bridge links."""
    grouped = defaultdict(lambda: {"native": [], "token": []})
    for edge in native_edges:
        if edge.get("tx_hash"):
            grouped[str(edge["tx_hash"]).lower()]["native"].append(edge)
    for edge in token_edges:
        if edge.get("tx_hash"):
            grouped[str(edge["tx_hash"]).lower()]["token"].append(edge)
    out = []
    for tx_hash, events in grouped.items():
        tokens = events["token"]
        native = events["native"]
        if not tokens:
            continue
        contracts = sorted({str(edge.get("contract_address") or "").lower() for edge in tokens if edge.get("contract_address")})
        assets = sorted({str(edge.get("asset") or "").upper() for edge in tokens if edge.get("asset")})
        out.append({
            "tx_hash": tx_hash,
            "evidence_url": "https://etherscan.io/tx/" + tx_hash,
            "classification": "multi_asset_transfer_evidence" if len(contracts) > 1 else "erc20_transfer_evidence",
            "native_edges_observed": len(native),
            "token_edges_observed": len(tokens),
            "distinct_token_contracts": contracts,
            "asset_symbols": assets,
            "execution_semantics_confirmed": False,
            "swap_confirmed": False,
            "bridge_confirmed": False,
            "limitations": "Transaction-level co-occurrence does not establish swap, bridge, net economic value, or ordering of internal calls.",
        })
    return out[:100]
