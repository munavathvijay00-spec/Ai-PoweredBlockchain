"""Bounded address retention. No deletion unless explicitly enabled.

Only addresses older than the transaction window and without references or
intelligence metadata qualify. Unexpected foreign keys fail closed.
"""
from loguru import logger


async def prune_addresses(db, *, enabled=False, batch_size=250, minutes=30):
    if not 1 <= batch_size <= 1000 or minutes < 30:
        raise ValueError("Invalid retention limits")
    # A production database may have additional FK relationships not in init.sql.
    # Never delete if an unrecognized table references addresses.
    references = await db.fetch("""
        SELECT DISTINCT con.conrelid::regclass::text AS table_name
        FROM pg_constraint con
        WHERE con.contype = 'f' AND con.confrelid = 'addresses'::regclass
    """)
    referenced_tables = {r["table_name"].split(".")[-1] for r in references}
    unexpected = referenced_tables - {"transactions", "alerts", "address_transactions"}
    if unexpected:
        logger.warning(f"Address retention skipped: unexpected FK tables {sorted(unexpected)}")
        return 0

    # Legacy deployments have address_transactions; fresh init.sql deployments don't.
    has_links = "address_transactions" in referenced_tables
    links_guard = """
        AND NOT EXISTS (
            SELECT 1 FROM address_transactions atx WHERE atx.address_id = a.id
        )
    """ if has_links else ""

    # Count with same protection criteria as deletion.
    conditions = f"""
        a.last_seen < NOW() - ($1::int * INTERVAL '1 minute')
        AND a.first_seen < NOW() - ($1::int * INTERVAL '1 minute')
        AND NOT EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.from_address_id = a.id OR t.to_address_id = a.id
        )
        AND NOT EXISTS (SELECT 1 FROM alerts al WHERE al.address_id = a.id)
        AND NOT EXISTS (SELECT 1 FROM blacklist bl WHERE bl.address = a.address)
        AND a.label IS NULL
        AND a.is_blacklisted IS NOT TRUE
        AND COALESCE(a.risk_score, 0) = 0
        AND COALESCE(a.metadata, '{{}}'::jsonb) = '{{}}'::jsonb
        {links_guard}
    """
    if not enabled:
        count = await db.fetchval(f"SELECT COUNT(*) FROM addresses a WHERE {conditions}", minutes)
        logger.info(f"Address retention dry-run: {count} eligible, no rows deleted")
        return 0

    # Limit each pass to avoid locking large sections of a busy database.
    # Recheck all conditions at deletion time; SKIP LOCKED prevents contention.
    result = await db.execute(f"""
        WITH candidates AS (
            SELECT a.id FROM addresses a
            WHERE {conditions}
            ORDER BY a.last_seen, a.id
            LIMIT $2
            FOR UPDATE OF a SKIP LOCKED
        )
        DELETE FROM addresses a USING candidates c
        WHERE a.id = c.id
    """, minutes, batch_size)
    deleted = int(result.split()[-1])
    logger.info(f"Address retention: removed {deleted} unreferenced addresses")
    return deleted
