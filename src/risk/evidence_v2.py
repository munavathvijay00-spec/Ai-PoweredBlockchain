"""Risk v2: evidence classification independent of historical numeric scores.

No probability calibration is claimed until representative labeled validation exists.
"""
ENGINE_VERSION = "evidence-v2.0"
AMOUNT_FACTORS = frozenset({
    "whale_transaction", "large_transaction", "notable_transaction",
    "medium_transaction", "unusual_value", "zero_value",
})
BEHAVIOR_FACTORS = frozenset({
    "same_block_fan_out", "same_block_repeated_transfers",
    "bursty_activity", "ping_pong_pattern",
})


def assess_evidence(factors, tx_hash=None):
    """Classify observed signals, preserving a trace to their originating transaction."""
    facts = []
    behavioral = []
    unverified = []
    for factor in factors or []:
        if not isinstance(factor, dict):
            continue
        name = factor.get("factor", "")
        record = {
            "factor": name,
            "description": factor.get("reason", ""),
            "source_tx_hash": factor.get("tx_hash") or tx_hash,
            "source": factor.get("source") or "legacy_scoring_factor",
        }
        if name in AMOUNT_FACTORS:
            facts.append(record)
        elif name in BEHAVIOR_FACTORS:
            behavioral.append(record)
        else:
            unverified.append(record)
    if behavioral:
        level = "review"
        confidence = "limited"
        rationale = "Observed behavioral indicators require contextual investigation."
    elif facts:
        level = "insufficient_evidence"
        confidence = "limited"
        rationale = "Transfer amount or contract-call type alone does not establish suspicious behavior."
    else:
        level = "insufficient_evidence"
        confidence = "unknown"
        rationale = "No qualifying behavioral evidence is available."
    return {
        "engine_version": ENGINE_VERSION,
        "assessment": level,
        "confidence": confidence,
        "calibrated": False,
        "probability": None,
        "rationale": rationale,
        "observed_facts": facts,
        "behavioral_indicators": behavioral,
        "unverified_indicators": unverified,
        "limitations": [
            "This is not a finding of wrongdoing.",
            "Historical factor coverage may be incomplete.",
            "False-positive and false-negative rates have not been established.",
        ],
    }
