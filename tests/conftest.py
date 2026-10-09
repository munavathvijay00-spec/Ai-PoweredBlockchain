"""
Shared pytest fixtures.
Provides test database, mock clients, and sample data.
"""
import asyncio
import pytest
import asyncpg
from typing import Dict

from src.utils.config import get_settings


# ==============================================================
# EVENT LOOP (for async tests)
# ==============================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==============================================================
# DATABASE FIXTURES
# ==============================================================

@pytest.fixture(scope="session")
async def test_db_pool():
    """Create a connection pool to the test database."""
    settings = get_settings()
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=5,
    )
    yield pool
    await pool.close()


@pytest.fixture
async def clean_db(test_db_pool):
    """Truncate all tables before each test."""
    async with test_db_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE TABLE alerts, address_transactions, transactions, addresses 
            RESTART IDENTITY CASCADE
        """)
        # Add blacklist entry for testing
        await conn.execute("""
            INSERT INTO blacklist (address, reason, source) 
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
        """, "0x0000000000000000000000000000000000000000", "test null address", "test")
    yield


# ==============================================================
# SAMPLE DATA
# ==============================================================

@pytest.fixture
def sample_tx() -> Dict:
    """A valid normalized transaction dict."""
    from datetime import datetime
    return {
        'hash': '0x' + 'a' * 64,
        'from_address': '0x' + '1' * 40,
        'to_address': '0x' + '2' * 40,
        'value': 10 * 10**18,  # 10 ETH in wei
        'gas_price': 30 * 10**9,
        'gas_used': 21000,
        'block_number': 26000000,
        'timestamp': datetime(2026, 10, 9, 12, 0, 0),
        'status': 'confirmed',
        'risk_score': 0,
    }


@pytest.fixture
def sample_raw_tx() -> Dict:
    """A raw Web3-style transaction (with bytes, etc.)."""
    from datetime import datetime
    return {
        'hash': bytes.fromhex('a' * 64),
        'from': '0x' + '1' * 40,
        'to': '0x' + '2' * 40,
        'value': 10 * 10**18,
        'gasPrice': 30 * 10**9,
        'gas': 21000,
        'blockNumber': 26000000,
    }


@pytest.fixture
def sample_block() -> Dict:
    """A minimal block dict."""
    return {
        'number': 26000000,
        'timestamp': 1728460800,
        'hash': bytes.fromhex('b' * 64),
    }