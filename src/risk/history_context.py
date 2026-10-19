"""Bounded recent activity context for behavioral scoring.

One query loads only retained transactions touching addresses in the current block.
This is explicitly recent retained context, not complete wallet history.
"""
from collections import defaultdict


async def load_recent_activity(db, addresses, before_block: int, *, minutes: int = 30, per_address: int = 100):
    if not addresses:
        return {}
    if minutes < 1 or minutes > 1440 or per_address < 1 or per_address > 500:
        raise ValueError("invalid recent-activity bounds")
    normalized = sorted({str(a).lower() for a in addresses if a})
    # Bound rows returned by SQL before per-address Python filtering.
    # This safety cap does not establish complete history coverage.
    query_limit = min(50000, max(1000, len(normalized) * per_address * 2))
    rows = await db.fetch(
        """
        SELECT t.hash, t.value, t.timestamp, t.block_number,
               af.address AS from_address, at.address AS to_address
        FROM transactions t
        JOIN addresses af ON af.id=t.from_address_id
        JOIN addresses at ON at.id=t.to_address_id
        WHERE t.block_number < $2
          AND t.timestamp >= NOW() - ($3::int * INTERVAL '1 minute')
          AND (af.address = ANY($1::text[]) OR at.address = ANY($1::text[]))
        ORDER BY t.timestamp DESC, t.id DESC
        LIMIT $4
        """,
        normalized, int(before_block), int(minutes), query_limit,
    )
    histories = defaultdict(list)
    targets = set(normalized)
    for row in rows:
        src = row["from_address"].lower()
        dst = row["to_address"].lower()
        base = {
            "hash": row["hash"],
            "value": int(row.get("value") or 0),
            "timestamp": row["timestamp"],
            "block_number": int(row["block_number"]),
            "from_address": src,
            "to_address": dst,
        }
        if src in targets and len(histories[src]) < per_address:
            histories[src].append({**base, "direction": "outgoing", "counterparty": dst})
        if dst in targets and len(histories[dst]) < per_address:
            histories[dst].append({**base, "direction": "incoming", "counterparty": src})
    return dict(histories)
