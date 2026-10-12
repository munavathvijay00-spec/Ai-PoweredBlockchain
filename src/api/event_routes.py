"""On-demand, bounded Ethereum receipt inspection; no database writes."""
import asyncio
import re

from fastapi import APIRouter, HTTPException
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider

from src.blockchain.event_decoder import decode_receipt
from src.utils.config import get_settings

router = APIRouter(prefix="/api", tags=["on-chain events"])
HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
# Keep public API traffic from exhausting the shared RPC quota.
_slots = asyncio.Semaphore(3)


@router.get("/transactions/{tx_hash}/events")
async def transaction_events(tx_hash: str):
    """Decode a mined receipt, capped at 500 logs; does not claim verified token metadata."""
    if not HASH.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail="Expected a 0x-prefixed 32-byte transaction hash")
    try:
        async with _slots:
            provider = AsyncHTTPProvider(get_settings().ethereum_rpc_url,
                                         request_kwargs={"timeout": 8})
            w3 = AsyncWeb3(provider)
            try:
                receipt = await asyncio.wait_for(w3.eth.get_transaction_receipt(tx_hash), timeout=10)
            finally:
                await provider.disconnect()
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Ethereum RPC timed out")
    except Exception as exc:
        # Do not leak RPC URLs or provider API keys through exception messages.
        from web3.exceptions import TransactionNotFound
        if isinstance(exc, TransactionNotFound):
            raise HTTPException(status_code=404, detail="Transaction receipt not found")
        raise HTTPException(status_code=502, detail="Ethereum RPC receipt lookup failed")
    return decode_receipt(dict(receipt))
