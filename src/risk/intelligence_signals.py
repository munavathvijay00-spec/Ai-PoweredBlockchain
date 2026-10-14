"""Risk factors derived only from source-attributed address intelligence."""


def apply_verified_intelligence(result: dict, tx: dict, verified_matches: dict) -> dict:
    """Escalate exact verified-address matches without inferring ownership or intent.

    `verified_matches` is keyed by normalized Ethereum address and originates from
    verified_address_intelligence. A match means only that this exact address is
    present in the cited source. It is not proof that the counterparty/user owns,
    controls, or shares the listed entity's intent.
    """
    factors = list(result.get("factors") or [])
    matches = []
    for role, address in (
        ("sender", tx.get("from_address")),
        ("recipient", tx.get("to_address")),
    ):
        if not address:
            continue
        match = verified_matches.get(str(address).lower())
        if match:
            matches.append((role, str(address).lower(), match))

    if not matches:
        return {"score": int(result.get("score", 0)), "factors": factors}

    for role, address, match in matches:
        source = match.get("source") or "verified_address_intelligence"
        entity_name = match.get("entity_name") or "source-listed entity"
        factors.append({
            "factor": "verified_sanctions_match",
            "points": 100,
            "reason": (
                f"Exact {role} address match in verified source {source}: {entity_name}. "
                "This is a sanctions-review signal, not proof of ownership or wrongdoing."
            ),
            "source": source,
            "entity_id": match.get("entity_id"),
            "entity_name": entity_name,
            "matched_address": address,
            "matched_role": role,
            "checked_at": str(match.get("checked_at")) if match.get("checked_at") else None,
        })

    return {"score": 100, "factors": factors}
