"""Shared read-only investigation tools for specialist agents.

These helpers keep facts grounded in Ethereum RPC or retained database evidence. Agents
must not invent labels, intent, ownership, or historical coverage that is not returned by
these tools.
"""
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from src.blockchain.client import BlockchainClient
from src.database.connection import get_db
from src.database.repositories import AddressRepository, TransactionRepository


class AgentTools:
    def __init__(self):
        self._client: Optional[BlockchainClient] = None

    async def _get_client(self) -> BlockchainClient:
        if self._client is None:
            self._client = BlockchainClient()
            await self._client.connect()
        return self._client

    async def get_latest_block_number(self) -> int:
        client = await self._get_client()
        return await client.get_latest_block_number()

    async def get_eth_balance(self, address: str) -> float:
        client = await self._get_client()
        wei = await client.w3.eth.get_balance(address)
        return wei / 10**18

    async def get_transaction_count(self, address: str) -> int:
        db = await get_db()
        return int(await db.fetchval("""
            SELECT COUNT(*) FROM transactions t
            JOIN addresses a ON a.id = t.from_address_id OR a.id = t.to_address_id
            WHERE a.address = $1
        """, address.lower()) or 0)

    async def get_address_first_seen(self, address: str) -> Optional[str]:
        db = await get_db()
        result = await db.fetchval("SELECT first_seen FROM addresses WHERE address = $1", address.lower())
        return str(result) if result else None

    async def get_recent_transactions(self, address: str, limit: int = 100) -> List[Dict]:
        db = await get_db()
        rows = await db.fetch("""
            SELECT t.hash, a_from.address AS from_address, a_to.address AS to_address,
                   t.value, t.block_number, t.timestamp, t.risk_score,
                   t.risk_factors, t.ai_explanation
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE a_from.address = $1 OR a_to.address = $1
            ORDER BY t.timestamp DESC, t.id DESC
            LIMIT $2
        """, address.lower(), limit)
        return [dict(r) for r in rows]

    async def is_blacklisted(self, address: str) -> bool:
        db = await get_db()
        return await AddressRepository(db).is_blacklisted(address)

    async def get_entity_matches(self, addresses: List[str]) -> Dict[str, List[Dict]]:
        db = await get_db()
        return await AddressRepository(db).get_entity_matches(addresses)

    async def get_transaction_by_hash(self, tx_hash: str) -> Optional[Dict]:
        db = await get_db()
        repo = TransactionRepository(db, AddressRepository(db))
        row = await repo.get_by_hash(tx_hash)
        return dict(row) if row else None

    async def get_address_profile(self, address: str) -> Dict:
        """Bounded retained-window profile plus current ETH balance."""
        normalized = address.lower()
        db = await get_db()
        row = await db.fetchrow("""
            SELECT
              COUNT(*) FILTER (WHERE af.address=$1) AS outgoing_count,
              COUNT(*) FILTER (WHERE at.address=$1) AS incoming_count,
              COUNT(DISTINCT CASE WHEN af.address=$1 THEN at.address ELSE af.address END) AS unique_counterparties,
              COALESCE(SUM(CASE WHEN af.address=$1 THEN t.value ELSE 0 END),0) AS outgoing_wei,
              COALESCE(SUM(CASE WHEN at.address=$1 THEN t.value ELSE 0 END),0) AS incoming_wei,
              MAX(t.risk_score) AS max_risk_score,
              AVG(t.risk_score)::float AS avg_risk_score,
              MIN(t.timestamp) AS retained_first_seen,
              MAX(t.timestamp) AS retained_last_seen
            FROM transactions t
            JOIN addresses af ON af.id=t.from_address_id
            JOIN addresses at ON at.id=t.to_address_id
            WHERE af.address=$1 OR at.address=$1
        """, normalized)
        balance = await self.get_eth_balance(normalized)
        entity_matches = await self.get_entity_matches([normalized])
        return {
            "address": normalized,
            "balance_eth": balance,
            "outgoing_count": int(row["outgoing_count"] or 0),
            "incoming_count": int(row["incoming_count"] or 0),
            "unique_counterparties": int(row["unique_counterparties"] or 0),
            "outgoing_wei": str(row["outgoing_wei"] or 0),
            "incoming_wei": str(row["incoming_wei"] or 0),
            "max_risk_score": int(row["max_risk_score"] or 0),
            "avg_risk_score": float(row["avg_risk_score"] or 0),
            "retained_first_seen": str(row["retained_first_seen"]) if row["retained_first_seen"] else None,
            "retained_last_seen": str(row["retained_last_seen"]) if row["retained_last_seen"] else None,
            "entity_matches": entity_matches.get(normalized, []),
            "coverage_note": "Counts summarize only transactions retained by ChainScope; balance is current RPC state.",
        }

    async def get_transaction_context(self, tx_hash: str, neighbor_limit: int = 12) -> Optional[Dict]:
        tx = await self.get_transaction_by_hash(tx_hash)
        if not tx:
            return None
        addresses = [tx.get("from_address"), tx.get("to_address")]
        matches = await self.get_entity_matches([a for a in addresses if a])
        db = await get_db()
        neighbors = await db.fetch("""
            SELECT t.hash, af.address AS from_address, at.address AS to_address,
                   t.value, t.block_number, t.timestamp, t.risk_score
            FROM transactions t
            JOIN addresses af ON af.id=t.from_address_id
            JOIN addresses at ON at.id=t.to_address_id
            WHERE t.hash <> $1 AND (
              af.address = ANY($2::text[]) OR at.address = ANY($2::text[])
            )
            ORDER BY ABS(t.block_number - $3), t.timestamp DESC
            LIMIT $4
        """, tx_hash, [a.lower() for a in addresses if a], int(tx.get("block_number") or 0), neighbor_limit)
        return {"transaction": tx, "entity_matches": matches, "nearby_activity": [dict(r) for r in neighbors]}

    async def find_counterparties(self, address: str, limit: int = 10) -> List[str]:
        db = await get_db()
        rows = await db.fetch("""
            SELECT counterparty, COUNT(*) AS cnt FROM (
              SELECT at.address AS counterparty FROM transactions t
              JOIN addresses af ON t.from_address_id=af.id
              JOIN addresses at ON t.to_address_id=at.id
              WHERE af.address=$1
              UNION ALL
              SELECT af.address AS counterparty FROM transactions t
              JOIN addresses af ON t.from_address_id=af.id
              JOIN addresses at ON t.to_address_id=at.id
              WHERE at.address=$1
            ) q
            GROUP BY counterparty ORDER BY cnt DESC, counterparty LIMIT $2
        """, address.lower(), limit)
        return [r["counterparty"] for r in rows]

    async def analyze_address_patterns(self, address: str, limit: int = 120) -> Dict:
        """Compute explainable graph/temporal motifs from retained transactions."""
        normalized = address.lower()
        txs = await self.get_recent_transactions(normalized, limit=limit)
        outgoing = [t for t in txs if str(t.get("from_address", "")).lower() == normalized]
        incoming = [t for t in txs if str(t.get("to_address", "")).lower() == normalized]
        out_cp = Counter(str(t.get("to_address", "")).lower() for t in outgoing if t.get("to_address"))
        in_cp = Counter(str(t.get("from_address", "")).lower() for t in incoming if t.get("from_address"))
        repeated_amounts = Counter(str(t.get("value")) for t in txs if t.get("value") is not None)

        timestamps = []
        for tx in txs:
            ts = tx.get("timestamp")
            if isinstance(ts, datetime):
                timestamps.append(ts)
        timestamps.sort()
        max_in_10m = 0
        left = 0
        for right, ts in enumerate(timestamps):
            while left <= right and (ts - timestamps[left]).total_seconds() > 600:
                left += 1
            max_in_10m = max(max_in_10m, right - left + 1)

        reciprocal = sorted(set(out_cp).intersection(in_cp))
        fan_out = len(out_cp)
        fan_in = len(in_cp)
        repeats = [{"value_wei": value, "count": count} for value, count in repeated_amounts.most_common(5) if count >= 3]
        signals = []
        if max_in_10m >= 10:
            signals.append({"type": "bursty_activity", "severity": "review", "observed": max_in_10m, "window_minutes": 10})
        if fan_out >= 10:
            signals.append({"type": "fan_out", "severity": "review", "unique_outgoing_counterparties": fan_out})
        if fan_in >= 10:
            signals.append({"type": "fan_in", "severity": "review", "unique_incoming_counterparties": fan_in})
        if reciprocal:
            signals.append({"type": "reciprocal_flow", "severity": "context", "counterparties": reciprocal[:10]})
        if repeats:
            signals.append({"type": "repeated_amounts", "severity": "context", "amounts": repeats})

        return {
            "address": normalized,
            "sample_size": len(txs),
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
            "fan_out": fan_out,
            "fan_in": fan_in,
            "max_transactions_in_10m": max_in_10m,
            "reciprocal_counterparties": reciprocal[:10],
            "repeated_amounts": repeats,
            "signals": signals,
            "coverage_note": "Pattern analysis is bounded to retained ChainScope transactions and is not a fraud verdict.",
        }

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None


_tools: Optional[AgentTools] = None


def get_tools() -> AgentTools:
    global _tools
    if _tools is None:
        _tools = AgentTools()
    return _tools
