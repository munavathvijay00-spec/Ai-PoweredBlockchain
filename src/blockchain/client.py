"""
Web3 client for Ethereum interaction.
Handles connection, retries, and common blockchain operations.
"""
import asyncio
from typing import Optional, Dict, List
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings


class BlockchainClient:
    """
    Async Web3 client for Ethereum.
    
    Design decisions:
    - Async: Won't block on slow RPC calls
    - Retry logic: RPC providers have transient failures
    - Logging: Debug production issues
    """
    
    def __init__(self, rpc_url: Optional[str] = None):
        settings = get_settings()
        self.rpc_url = rpc_url or settings.ethereum_rpc_url
        self.w3: Optional[AsyncWeb3] = None
    
    async def connect(self) -> bool:
        """Establish connection to the blockchain node."""
        try:
            provider = AsyncHTTPProvider(self.rpc_url)
            self.w3 = AsyncWeb3(provider)
            
            # Verify connection
            is_connected = await self.w3.is_connected()
            if is_connected:
                chain_id = await self.w3.eth.chain_id
                if chain_id != 1:
                    logger.error(f"Refusing Ethereum mainnet ingestion: RPC returned chain_id={chain_id}")
                    await self.close()
                    return False
                block_number = await self.w3.eth.block_number
                logger.success(
                    f"✅ Connected to chain {chain_id} "
                    f"(latest block: {block_number:,})"
                )
                return True
            else:
                logger.error("❌ Failed to connect")
                return False
                
        except Exception as e:
            logger.exception(f"Connection error: {e}")
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_latest_block_number(self) -> int:
        """Get latest block number with retry logic."""
        return await self.w3.eth.block_number
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
    async def get_block(self, block_number: int, full_transactions: bool = False) -> Dict:
        """Fetch block by number."""
        block = await self.w3.eth.get_block(
            block_number, 
            full_transactions=full_transactions
        )
        return dict(block)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
    async def get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """Fetch transaction by hash."""
        try:
            tx = await self.w3.eth.get_transaction(tx_hash)
            return dict(tx)
        except Exception as e:
            logger.warning(f"Transaction {tx_hash} not found: {e}")
            return None
    
    async def get_transactions_in_block(self, block_number: int) -> List[Dict]:
        """Get all transactions in a block."""
        block = await self.get_block(block_number, full_transactions=True)
        return [dict(tx) for tx in block.get('transactions', [])]
    
    async def close(self):
        """Clean up resources."""
        if self.w3 and self.w3.provider:
            try:
                await self.w3.provider.disconnect()
            except Exception:
                pass
        logger.info("Blockchain client closed")