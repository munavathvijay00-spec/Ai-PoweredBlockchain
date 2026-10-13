"""Async Ethereum mainnet RPC client with fail-closed chain validation and metrics."""
import time
from typing import Optional, Dict, List
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings
from src.metrics import rpc_requests_total, rpc_request_duration_seconds, rpc_connected


class BlockchainClient:
    def __init__(self, rpc_url: Optional[str] = None):
        settings = get_settings()
        self.rpc_url = rpc_url or settings.ethereum_rpc_url
        self.w3: Optional[AsyncWeb3] = None

    async def _observe(self, method: str, operation):
        start = time.monotonic()
        try:
            result = await operation()
            rpc_requests_total.labels(method=method, status="success").inc()
            return result
        except Exception:
            rpc_requests_total.labels(method=method, status="error").inc()
            raise
        finally:
            rpc_request_duration_seconds.labels(method=method).observe(time.monotonic() - start)

    async def connect(self) -> bool:
        try:
            provider = AsyncHTTPProvider(self.rpc_url)
            self.w3 = AsyncWeb3(provider)
            is_connected = await self._observe("is_connected", self.w3.is_connected)
            if not is_connected:
                rpc_connected.set(0)
                logger.error("RPC connection check failed")
                return False
            chain_id = await self._observe("eth_chainId", lambda: self.w3.eth.chain_id)
            if chain_id != 1:
                rpc_connected.set(0)
                logger.error(f"Refusing Ethereum mainnet ingestion: RPC returned chain_id={chain_id}")
                await self.close()
                return False
            block_number = await self._observe("eth_blockNumber", lambda: self.w3.eth.block_number)
            rpc_connected.set(1)
            logger.success(f"Connected to Ethereum mainnet (latest block: {block_number:,})")
            return True
        except Exception as exc:
            rpc_connected.set(0)
            logger.exception(f"Connection error: {exc}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_latest_block_number(self) -> int:
        return await self._observe("eth_blockNumber", lambda: self.w3.eth.block_number)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_block(self, block_number: int, full_transactions: bool = False) -> Dict:
        async def request():
            return await self.w3.eth.get_block(block_number, full_transactions=full_transactions)
        block = await self._observe("eth_getBlockByNumber", request)
        return dict(block)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_transaction(self, tx_hash: str) -> Optional[Dict]:
        async def request():
            return await self.w3.eth.get_transaction(tx_hash)
        try:
            tx = await self._observe("eth_getTransactionByHash", request)
            return dict(tx)
        except Exception as exc:
            logger.warning(f"Transaction {tx_hash} lookup failed: {type(exc).__name__}")
            return None

    async def get_transactions_in_block(self, block_number: int) -> List[Dict]:
        block = await self.get_block(block_number, full_transactions=True)
        return [dict(tx) for tx in block.get("transactions", [])]

    async def close(self):
        if self.w3 and self.w3.provider:
            try:
                await self.w3.provider.disconnect()
            except Exception:
                pass
        logger.info("Blockchain client closed")
