"""
Repositories: organized database operations.
Separates SQL logic from business logic.
"""
import json
from typing import Optional, List, Dict
from loguru import logger

from src.database.connection import Database


class AddressRepository:
    """All address-related database operations."""

    def __init__(self, db: Database):
        self.db = db

    async def get_or_create(self, address: str) -> int:
        """Get address ID, creating if not exists."""
        query = """
            INSERT INTO addresses (address) 
            VALUES ($1) 
            ON CONFLICT (address) DO UPDATE 
            SET last_seen = CURRENT_TIMESTAMP
            RETURNING id
        """
        return await self.db.fetchval(query, address.lower())

    async def get_by_address(self, address: str) -> Optional[Dict]:
        """Fetch address by string value."""
        query = """
            SELECT id, address, first_seen, last_seen, 
                   label, is_blacklisted, risk_score
            FROM addresses 
            WHERE address = $1
        """
        return await self.db.fetchrow(query, address.lower())

    async def is_blacklisted(self, address: str) -> bool:
        """Check if address is in blacklist."""
        query = "SELECT EXISTS(SELECT 1 FROM blacklist WHERE address = $1)"
        return await self.db.fetchval(query, address.lower())

    async def get_blacklisted_set(self, addresses: list) -> set:
        """Return set of blacklisted addresses from the given list."""
        if not addresses:
            return set()
        addresses = [a.lower() for a in addresses]
        query = "SELECT address FROM blacklist WHERE address = ANY($1::text[])"
        rows = await self.db.fetch(query, addresses)
        return {row['address'] for row in rows}

    async def bulk_get_or_create_addresses(self, addresses: list) -> dict:
        """
        Insert multiple addresses at once, return {address: id} map.
        Uses PostgreSQL unnest for one-query bulk insert.
        """
        if not addresses:
            return {}
        
        addresses = [a.lower() for a in addresses]
        
        query = """
            WITH input_addresses(address) AS (
                SELECT unnest($1::text[])
            ),
            inserted AS (
                INSERT INTO addresses (address)
                SELECT address FROM input_addresses
                ON CONFLICT (address) DO NOTHING
                RETURNING id, address
            )
            SELECT address, id FROM inserted
            UNION
            SELECT a.address, a.id 
            FROM addresses a
            WHERE a.address = ANY($1::text[])
        """
        rows = await self.db.fetch(query, addresses)
        return {row['address']: row['id'] for row in rows}

    async def count(self) -> int:
        """Total addresses tracked."""
        return await self.db.fetchval("SELECT COUNT(*) FROM addresses")

    async def list_all(self, limit: int = 10) -> List[Dict]:
        """List recent addresses."""
        query = """
            SELECT address, first_seen, risk_score
            FROM addresses
            ORDER BY first_seen DESC
            LIMIT $1
        """
        return await self.db.fetch(query, limit)


class TransactionRepository:
    """All transaction-related database operations."""

    def __init__(self, db: Database, address_repo: AddressRepository):
        self.db = db
        self.addresses = address_repo

    async def create(self, tx: Dict) -> int:
        """Insert a transaction."""
        from_id = await self.addresses.get_or_create(tx['from_address'])
        to_id = await self.addresses.get_or_create(tx['to_address'])

        query = """
            INSERT INTO transactions 
            (hash, from_address_id, to_address_id, value, 
             block_number, timestamp, status, risk_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (hash) DO UPDATE 
            SET risk_score = EXCLUDED.risk_score
            RETURNING id
        """
        return await self.db.fetchval(
            query,
            tx['hash'], from_id, to_id, tx['value'],
            tx['block_number'], tx['timestamp'],
            tx.get('status', 'confirmed'), tx.get('risk_score', 0),
        )

    async def bulk_create_transactions(self, txs: list, addr_map: dict) -> int:
        """Bulk insert multiple transactions at once."""
        if not txs:
            return 0

        hashes, from_ids, to_ids = [], [], []
        values, gas_prices, gas_useds = [], [], []
        block_numbers, timestamps = [], []
        statuses, risk_scores = [], []

        for tx in txs:
            from_id = addr_map.get(tx['from_address'].lower())
            to_id = addr_map.get(tx['to_address'].lower())
            if not from_id or not to_id:
                continue

            hashes.append(tx['hash'])
            from_ids.append(from_id)
            to_ids.append(to_id)
            values.append(tx['value'])
            gas_prices.append(tx.get('gas_price', 0))
            gas_useds.append(tx.get('gas_used', 0))
            block_numbers.append(tx['block_number'])
            timestamps.append(tx['timestamp'])
            statuses.append(tx.get('status', 'confirmed'))
            risk_scores.append(tx.get('risk_score', 0))

        if not hashes:
            return 0

        query = """
            INSERT INTO transactions 
            (hash, from_address_id, to_address_id, value, gas_price, gas_used,
             block_number, timestamp, status, risk_score)
            SELECT * FROM unnest(
                $1::text[], $2::bigint[], $3::bigint[], $4::numeric[],
                $5::numeric[], $6::numeric[], $7::bigint[], $8::timestamp[],
                $9::text[], $10::smallint[]
            )
            ON CONFLICT (hash) DO NOTHING
        """
        await self.db.execute(
            query,
            hashes, from_ids, to_ids, values, gas_prices, gas_useds,
            block_numbers, timestamps, statuses, risk_scores,
        )
        return len(hashes)

    async def bulk_update_risk_scores(self, scores: list) -> int:
        """Update risk scores for multiple transactions."""
        if not scores:
            return 0

        hashes = [s['hash'] for s in scores]
        risk_scores = [s['score'] for s in scores]
        factors_jsons = [json.dumps(s['factors']) for s in scores]

        query = """
            UPDATE transactions t
            SET risk_score = data.risk_score,
                risk_factors = data.factors::jsonb
            FROM (
                SELECT unnest($1::text[]) AS hash,
                       unnest($2::smallint[]) AS risk_score,
                       unnest($3::text[]) AS factors
            ) AS data
            WHERE t.hash = data.hash
        """
        await self.db.execute(query, hashes, risk_scores, factors_jsons)
        return len(scores)

    async def bulk_update_explanations(self, explanations: list) -> int:
        """Update AI explanations for multiple transactions."""
        if not explanations:
            return 0

        hashes = [e['hash'] for e in explanations]
        texts = [e['explanation'] for e in explanations]

        query = """
            UPDATE transactions t
            SET ai_explanation = data.explanation
            FROM (
                SELECT unnest($1::text[]) AS hash,
                       unnest($2::text[]) AS explanation
            ) AS data
            WHERE t.hash = data.hash
        """
        await self.db.execute(query, hashes, texts)
        return len(explanations)

    async def get_by_hash(self, tx_hash: str) -> Optional[Dict]:
        """Fetch a transaction by its hash."""
        query = """
            SELECT 
                t.hash,
                a_from.address AS from_address,
                a_to.address AS to_address,
                t.value, t.block_number, t.timestamp,
                t.status, t.risk_score, t.risk_factors, t.ai_explanation
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE t.hash = $1
        """
        return await self.db.fetchrow(query, tx_hash)

    async def list_recent(self, limit: int = 10) -> List[Dict]:
        """List recent transactions."""
        query = """
            SELECT 
                t.hash,
                a_from.address AS from_address,
                a_to.address AS to_address,
                t.value, t.block_number, t.timestamp, t.risk_score
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            ORDER BY t.timestamp DESC
            LIMIT $1
        """
        return await self.db.fetch(query, limit)

    async def list_all(self, limit: int = 1000) -> List[Dict]:
        """Fetch all transactions for batch risk scoring."""
        query = """
            SELECT 
                t.hash,
                a_from.address AS from_address,
                a_to.address AS to_address,
                t.value, t.block_number, t.timestamp, t.risk_score
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            ORDER BY t.block_number DESC
            LIMIT $1
        """
        return await self.db.fetch(query, limit)

    async def list_flagged(self, min_score: int = 20, limit: int = 100) -> List[Dict]:
        """Fetch flagged transactions."""
        query = """
            SELECT 
                t.hash,
                a_from.address AS from_address,
                a_to.address AS to_address,
                t.value, t.block_number, t.timestamp,
                t.risk_score, t.risk_factors, t.ai_explanation
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE t.risk_score >= $1
            ORDER BY t.risk_score DESC, t.timestamp DESC
            LIMIT $2
        """
        return await self.db.fetch(query, min_score, limit)

    async def count(self) -> int:
        """Total transactions stored."""
        return await self.db.fetchval("SELECT COUNT(*) FROM transactions")

    async def update_risk(self, tx_hash: str, score: int, factors: list) -> None:
        """Update risk score and factors for a transaction."""
        query = """
            UPDATE transactions 
            SET risk_score = $1, risk_factors = $2::jsonb
            WHERE hash = $3
        """
        await self.db.execute(query, score, json.dumps(factors), tx_hash)

    async def update_explanation(self, tx_hash: str, explanation: str) -> None:
        """Update AI-generated explanation for a transaction."""
        query = """
            UPDATE transactions 
            SET ai_explanation = $1
            WHERE hash = $2
        """
        await self.db.execute(query, explanation, tx_hash)