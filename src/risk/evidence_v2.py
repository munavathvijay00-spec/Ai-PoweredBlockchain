"""Risk v2: evidence classification independent of historical numeric scores.

No probability calibration is claimed until representative labeled validation exists.
"""
ENGINE_VERSION = "evidence-v2.1"
AMOUNT_FACTORS = frozenset({
    "whale_transaction", "large_transaction", "notable_transaction",
    "medium_transaction", "unusual_value", "zero_value",
})
BEHAVIOR_FACTORS = frozenset({
    "same_block_fan_out", "same_block_repeated_transfers",
    "bursty_activity", "ping_pong_pattern", "repeated_counterparty",
})
VERIFIED_ENTITY_FACTORS = frozenset({
    "verified_sanctions_match", "source_attributed_risk_entity_match",
})


def assess_evidence(factors, tx_hash=None):
    """Classify observed signals, preserving provenance and evidence category."""
    facts = []
    behavioral = []
    verified_entities = []
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
        if factor.get("source_url"):
            record["source_url"] = factor.get("source_url")
        if factor.get("entity_name"):
            record["entity_name"] = factor.get("entity_name")
        if factor.get("entity_type"):
            record["entity_type"] = factor.get("entity_type")
        if factor.get("matched_address"):
            record["matched_address"] = factor.get("matched_address")
        if factor.get("matched_role"):
            record["matched_role"] = factor.get("matched_role")

        if name in AMOUNT_FACTORS:
            facts.append(record)
        elif name in BEHAVIOR_FACTORS:
            behavioral.append(record)
        elif name in VERIFIED_ENTITY_FACTORS:
            verified_entities.append(record)
        else:
            unverified.append(record)

    if verified_entities and behavioral:
        level = "review"
        confidence = "limited"
        rationale = "Source-attributed exact-address intelligence and observed behavioral indicators both warrant contextual investigation."
    elif verified_entities:
        level = "review"
        confidence = "limited"
        rationale = "Source-attributed exact-address intelligence warrants contextual investigation; attribution is not proof of ownership or intent."
    elif behavioral:
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
        rationale = "No qualifying behavioral or source-attributed risk evidence is available."

    return {
        "engine_version": ENGINE_VERSION,
        "assessment": level,
        "confidence": confidence,
        "calibrated": False,
        "probability": None,
        "rationale": rationale,
        "observed_facts": facts,
        "behavioral_indicators": behavioral,
        "verified_entity_indicators": verified_entities,
        "unverified_indicators": unverified,
        "limitations": [
            "This is not a finding of wrongdoing.",
            "Address attribution does not establish beneficial ownership, transaction intent, or guilt.",
            "Historical factor and entity coverage may be incomplete.",
            "False-positive and false-negative rates apply only after an independent labelled evaluation is published.",
        ],
    }
