"""
Shared tools that agents can call.
Each method is a discrete capability (like OpenAI function calling).
"""
from typing import Dict, List, Optional
from loguru import logger

from src.blockchain.client import BlockchainClient
from src.database.connection import get_db
from src.database.repositories import AddressRepository, TransactionRepository


class AgentTools:
    """Collection of tools available to agents."""

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
        query = """
            SELECT COUNT(*) FROM transactions t
            JOIN addresses a ON a.id = t.from_address_id OR a.id = t.to_address_id
            WHERE a.address = $1
        """
        return await db.fetchval(query, address.lower())

    async def get_address_first_seen(self, address: str) -> Optional[str]:
        db = await get_db()
        query = "SELECT first_seen FROM addresses WHERE address = $1"
        result = await db.fetchval(query, address.lower())
        return str(result) if result else None

    async def get_recent_transactions(self, address: str, limit: int = 10) -> List[Dict]:
        db = await get_db()
        query = """
            SELECT 
                t.hash, a_from.address AS from_address,
                a_to.address AS to_address, t.value,
                t.block_number, t.risk_score
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE a_from.address = $1 OR a_to.address = $1
            ORDER BY t.block_number DESC
            LIMIT $2
        """
        rows = await db.fetch(query, address.lower(), limit)
        return [dict(r) for r in rows]

    async def is_blacklisted(self, address: str) -> bool:
        db = await get_db()
        addresses = AddressRepository(db)
        return await addresses.is_blacklisted(address)

    async def get_transaction_by_hash(self, tx_hash: str) -> Optional[Dict]:
        db = await get_db()
        addresses = AddressRepository(db)
        transactions = TransactionRepository(db, addresses)
        return await transactions.get_by_hash(tx_hash)

    async def detect_bursty_activity(self, address: str) -> bool:
        recent = await self.get_recent_transactions(address, limit=50)
        return len(recent) >= 10

    async def find_counterparties(self, address: str, limit: int = 10) -> List[str]:
        db = await get_db()
        query = """
            SELECT COUNT(*) as cnt, a_to.address
            FROM transactions t
            JOIN addresses a_from ON t.from_address_id = a_from.id
            JOIN addresses a_to ON t.to_address_id = a_to.id
            WHERE a_from.address = $1
            GROUP BY a_to.address
            ORDER BY cnt DESC
            LIMIT $2
        """
        rows = await db.fetch(query, address.lower(), limit)
        return [r['address'] for r in rows]

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
