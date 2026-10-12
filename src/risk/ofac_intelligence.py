"""Verified OFAC Ethereum address feed. No AI-generated blacklist entries.

Source: official OFAC SDN CSV (remarks contain 'Digital Currency Address - ETH').
Sync is fail-safe: an empty, malformed or failed download never clears prior data.
"""
import csv
import io
import re
import urllib.request
from datetime import datetime, timezone
from loguru import logger

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
SOURCE = "OFAC_SDN_ETH"
_ETH = re.compile(r"Digital Currency Address\s*-\s*ETH\s*[: ]\s*(0x[a-fA-F0-9]{40})(?![a-fA-F0-9])", re.I)
_ADDRESS = re.compile(r"^0x[a-f0-9]{40}$")


def parse_ofac_eth_csv(content: bytes) -> dict:
    """Extract only explicitly ETH-tagged 20-byte addresses from SDN remarks."""
    if len(content) > 25_000_000:
        raise ValueError("OFAC feed exceeds size limit")
    text = content.decode("utf-8-sig")
    matches = {}
    rows = csv.reader(io.StringIO(text))
    seen = 0
    for row in rows:
        if len(row) < 12:
            continue
        seen += 1
        # OFAC legacy SDN CSV: col 0 ent_num, col 1 SDN_Name, col 11 remarks.
        entity_id, name, remarks = row[0].strip(), row[1].strip(), row[11]
        if not entity_id.isdigit():
            continue
        for match in _ETH.finditer(remarks):
            address = match.group(1).lower()
            if _ADDRESS.fullmatch(address):
                matches[address] = (entity_id, name[:250])
    if seen < 1 or not matches:
        raise ValueError("OFAC feed has no valid Ethereum entries; refusing sync")
    return matches


def download_ofac_csv() -> bytes:
    request = urllib.request.Request(
        OFAC_SDN_CSV, headers={"User-Agent": "AI-PoweredBlockchain-OFAC-Sync/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f"OFAC returned HTTP {response.status}")
        payload = response.read(25_000_001)
    if len(payload) > 25_000_000:
        raise ValueError("OFAC feed exceeds size limit")
    return payload


async def ensure_intelligence_schema(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS verified_address_intelligence (
            source TEXT NOT NULL,
            address VARCHAR(42) NOT NULL,
            entity_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source, address)
        )
    """)


async def sync_ofac(db, payload: bytes):
    """Atomically replace only this source's matches; never modify manual blacklist."""
    matches = parse_ofac_eth_csv(payload)
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS verified_address_intelligence (
                    source TEXT NOT NULL,
                    address VARCHAR(42) NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (source, address)
                )
            """)
            previous_count = await conn.fetchval(
                "SELECT COUNT(*) FROM verified_address_intelligence WHERE source = $1", SOURCE
            )
            # Reject a sudden large drop: a partially downloaded CSV can be valid CSV.
            # Keep the last known-good sanctions snapshot until reviewed.
            if previous_count >= 10 and len(matches) < previous_count // 2:
                raise ValueError(
                    f"OFAC feed unexpectedly shrank from {previous_count} to "
                    f"{len(matches)} ETH addresses; preserving existing snapshot"
                )
            await conn.execute("DELETE FROM verified_address_intelligence WHERE source = $1", SOURCE)
            await conn.executemany("""
                INSERT INTO verified_address_intelligence
                    (source, address, entity_id, entity_name, checked_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, [(SOURCE, address, entity_id, name) for address, (entity_id, name) in matches.items()])
    logger.info(f"Verified intelligence: synced {len(matches)} OFAC Ethereum addresses")
    return len(matches)


async def refresh_ofac(db):
    """Network fetch outside DB transaction; failures leave last good snapshot."""
    import asyncio
    try:
        payload = await asyncio.to_thread(download_ofac_csv)
        return await sync_ofac(db, payload)
    except Exception as exc:
        logger.warning(f"OFAC refresh failed; previous verified snapshot preserved: {type(exc).__name__}: {exc}")
        return 0
