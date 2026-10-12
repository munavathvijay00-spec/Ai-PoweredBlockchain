"""Bounded, evidence-backed direct exposure to OFAC-listed Ethereum addresses."""
SOURCE = "OFAC_SDN_ETH"
MAX_EXPOSURES = 5000


async def ensure_exposure_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS wallet_direct_exposure (
            address VARCHAR(42) PRIMARY KEY,
            sanctioned_address VARCHAR(42) NOT NULL,
            evidence_tx_hash VARCHAR(66) NOT NULL,
            direction TEXT NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def find_direct_exposures(txs, verified_matches):
    """Only actual observed transfers create exposure; no inferred multi-hop links."""
    found = {}
    for tx in txs:
        sender = tx["from_address"].lower()
        recipient = tx["to_address"].lower()
        if sender == recipient:
            continue
        if sender in verified_matches and recipient not in verified_matches:
            found[recipient] = (sender, tx["hash"], "received_from_sanctioned")
        if recipient in verified_matches and sender not in verified_matches:
            found[sender] = (recipient, tx["hash"], "sent_to_sanctioned")
    return found


async def save_direct_exposures(db, exposures):
    """Persist and prune atomically, even on blocks with no new exposure."""
    async with db.acquire() as conn:
        async with conn.transaction():
            if exposures:
                await conn.executemany("""
                    INSERT INTO wallet_direct_exposure
                        (address, sanctioned_address, evidence_tx_hash, direction, observed_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (address) DO UPDATE SET
                        sanctioned_address = EXCLUDED.sanctioned_address,
                        evidence_tx_hash = EXCLUDED.evidence_tx_hash,
                        direction = EXCLUDED.direction,
                        observed_at = EXCLUDED.observed_at
                """, [(address, *evidence) for address, evidence in exposures.items()])
            await conn.execute("""
                DELETE FROM wallet_direct_exposure
                WHERE observed_at < NOW() - INTERVAL '7 days'
                   OR address IN (
                       SELECT address FROM wallet_direct_exposure
                       ORDER BY observed_at DESC, address DESC
                       OFFSET 5000
                   )
            """)


async def get_direct_exposures(db, addresses):
    if not addresses:
        return {}
    try:
        rows = await db.fetch("""
            SELECT e.address, e.sanctioned_address, e.evidence_tx_hash,
                   e.direction, e.observed_at
            FROM wallet_direct_exposure e
            JOIN verified_address_intelligence v
              ON v.address = e.sanctioned_address AND v.source = 'OFAC_SDN_ETH'
            WHERE e.address = ANY($1::text[])
              AND e.observed_at >= NOW() - INTERVAL '7 days'
        """, [a.lower() for a in addresses])
    except Exception:
        return {}
    return {row["address"]: dict(row) for row in rows}


def apply_exposure_risk(result, tx, exposure_matches, verified_matches):
    """Exposure is a risk signal, never a confirmed sanctions designation."""
    if result["score"] == 100:
        return result
    for address in {tx["from_address"].lower(), tx["to_address"].lower()}:
        if address in verified_matches:
            continue
        evidence = exposure_matches.get(address)
        if evidence:
            result["factors"].append({
                "factor": "direct_sanctions_counterparty_exposure",
                "points": 25,
                "reason": "Observed direct transfer with an OFAC-listed address; counterparty is not itself designated",
                "address": address,
                "sanctioned_address": evidence["sanctioned_address"],
                "evidence_tx_hash": evidence["evidence_tx_hash"],
                "direction": evidence["direction"],
                "source": SOURCE,
            })
            result["score"] = min(100, result["score"] + 25)
    return result
