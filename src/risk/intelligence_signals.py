"""Risk factors derived only from source-attributed exact-address intelligence.

Entity context and risk are deliberately separated. Common infrastructure such as
protocols, bridges, exchanges and custodians can be useful investigative context,
but its presence alone does not increase the transaction risk score. Only a small
set of source-attributed review categories can affect the score, and every factor
preserves provenance and cautions against ownership/intent inference.
"""

RISK_ENTITY_POINTS = {
    "sanctions": 100,
    "scam": 60,
    "phishing": 60,
    "exploit": 60,
    "mixer": 25,
}
MIN_SCORING_CONFIDENCE = 0.80


def _as_matches(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def apply_verified_intelligence(result: dict, tx: dict, verified_matches: dict) -> dict:
    """Apply source-attributed exact-address review signals without inferring intent.

    `verified_matches` is keyed by normalized Ethereum address and may contain one
    or more current attributions for each exact address. A match identifies only the
    address-level label supplied by the cited source; it does not establish that the
    transaction sender/recipient beneficially owns the entity, shares its intent, or
    engaged in wrongdoing.
    """
    score = int(result.get("score", 0) or 0)
    factors = list(result.get("factors") or [])
    seen = set()

    for role, raw_address in (
        ("sender", tx.get("from_address")),
        ("recipient", tx.get("to_address")),
    ):
        if not raw_address:
            continue
        address = str(raw_address).lower()
        for match in _as_matches(verified_matches.get(address)):
            entity_type = str(match.get("entity_type") or "sanctions").lower()
            source = str(match.get("source") or "verified_address_intelligence")
            entity_id = str(match.get("entity_id") or "")
            dedupe_key = (role, address, source, entity_id, entity_type)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            try:
                confidence = float(match.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            points = RISK_ENTITY_POINTS.get(entity_type)
            if points is None or confidence < MIN_SCORING_CONFIDENCE:
                # Useful entity context is exposed by the API, but benign/common
                # service categories and low-confidence rows do not alter risk.
                continue

            entity_name = match.get("entity_name") or "source-listed entity"
            source_url = match.get("source_url")
            verified_at = match.get("verified_at") or match.get("checked_at")

            if entity_type == "sanctions":
                factor_name = "verified_sanctions_match"
                reason = (
                    f"Exact {role} address match in source {source}: {entity_name}, labelled sanctions. "
                    "This is a sanctions-review signal, not proof of ownership or wrongdoing; "
                    "transaction intent still requires independent investigation."
                )
                score = 100
            else:
                factor_name = "source_attributed_risk_entity_match"
                reason = (
                    f"Exact {role} address match in source {source}: {entity_name}, labelled {entity_type}. "
                    "This source-attributed label warrants contextual review but does not prove this transaction is illicit."
                )
                score = min(100, score + points)

            factors.append({
                "factor": factor_name,
                "points": points,
                "reason": reason,
                "source": source,
                "source_url": source_url,
                "entity_id": match.get("entity_id"),
                "entity_name": entity_name,
                "entity_type": entity_type,
                "attribution_confidence": confidence,
                "matched_address": address,
                "matched_role": role,
                "verified_at": str(verified_at) if verified_at else None,
            })

    return {"score": score, "factors": factors}
