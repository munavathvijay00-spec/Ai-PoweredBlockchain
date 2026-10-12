"""Low-impact PostgreSQL storage diagnostics; no destructive maintenance."""
from loguru import logger


async def log_storage_health(db):
    """Identify tables and indexes consuming space without scanning their rows."""
    rows = await db.fetch("""
        SELECT relname AS table_name,
               pg_total_relation_size(relid) AS total_bytes,
               pg_relation_size(relid) AS heap_bytes,
               pg_indexes_size(relid) AS index_bytes,
               n_live_tup AS estimated_live,
               n_dead_tup AS estimated_dead,
               last_autovacuum
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 8
    """)
    for row in rows:
        logger.info(
            "Storage health: {} total={:.1f}MB heap={:.1f}MB indexes={:.1f}MB "
            "estimated_live={} estimated_dead={} last_autovacuum={}",
            row["table_name"], row["total_bytes"] / 1048576,
            row["heap_bytes"] / 1048576, row["index_bytes"] / 1048576,
            row["estimated_live"], row["estimated_dead"], row["last_autovacuum"],
        )
    size = await db.fetchval("SELECT pg_database_size(current_database())")
    logger.info("Storage health: database logical size={:.1f}MB (Railway volume may differ)",
                size / 1048576)
