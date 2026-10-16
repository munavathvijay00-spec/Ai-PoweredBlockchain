"""On-demand, bounded Ethereum receipt inspection; no database writes."""
import asyncio
import re

from fastapi import APIRouter, HTTPException
from loguru import logger
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound
from web3.providers.async_rpc import AsyncHTTPProvider

from src.blockchain.event_decoder import decode_receipt
from src.blockchain.token_metadata import resolve_metadata
from src.utils.config import get_settings

router = APIRouter(prefix="/api", tags=["on-chain events"])
HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
_slots = asyncio.Semaphore(3)


def _rpc_candidates() -> list[str]:
    settings = get_settings()
    urls: list[str] = []
    configured = settings.ethereum_rpc_url.strip()
    if configured:
        urls.append(configured)
    key = settings.alchemy_api_key.strip()
    if key and key.lower() not in {"not-set", "none", "null"}:
        alchemy = f"https://eth-mainnet.g.alchemy.com/v2/{key}"
        if alchemy not in urls:
            urls.append(alchemy)
    return urls


async def _receipt_from_rpc(tx_hash: str):
    last_error: Exception | None = None
    saw_not_found = False
    for rpc_url in _rpc_candidates():
        provider = AsyncHTTPProvider(rpc_url, request_kwargs={"timeout": 8})
        w3 = AsyncWeb3(provider)
        try:
            receipt = await asyncio.wait_for(w3.eth.get_transaction_receipt(tx_hash), timeout=10)
            return receipt, w3
        except TransactionNotFound as exc:
            saw_not_found = True
            last_error = exc
        except Exception as exc:
            last_error = exc
            logger.warning("Receipt RPC candidate failed for tx={} error_type={}", tx_hash, type(exc).__name__)
        # web3==6.15 AsyncHTTPProvider has no public disconnect()/close() method.
        # Its async session manager owns provider session lifecycle, so do not call a
        # non-existent cleanup method here. This previously converted successful RPC
        # receipt lookups into HTTP 500 responses during route finalization.
    if saw_not_found and isinstance(last_error, TransactionNotFound):
        raise last_error
    if isinstance(last_error, asyncio.TimeoutError):
        raise last_error
    raise RuntimeError("all Ethereum receipt RPC candidates failed") from last_error


@router.get("/transactions/{tx_hash}/events")
async def transaction_events(tx_hash: str):
    """Decode a mined receipt, capped at 500 logs; token metadata is best-effort only."""
    if not HASH.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail="Expected a 0x-prefixed 32-byte transaction hash")

    try:
        async with _slots:
            receipt, w3 = await _receipt_from_rpc(tx_hash)
            decoded = decode_receipt(dict(receipt))
            contracts = list(dict.fromkeys(
                event["contract"]
                for event in decoded["events"]
                if event.get("standard") == "ERC20-compatible" and event.get("contract")
            ))[:8]
            if contracts:
                try:
                    metadata = await asyncio.gather(
                        *(resolve_metadata(w3, address, receipt["blockNumber"]) for address in contracts),
                        return_exceptions=True,
                    )
                    by_contract = {
                        address: value
                        for address, value in zip(contracts, metadata)
                        if isinstance(value, dict)
                    }
                    for event in decoded["events"]:
                        details = by_contract.get(event.get("contract"))
                        if event.get("standard") == "ERC20-compatible" and details:
                            event.update(details)
                except Exception as exc:
                    logger.warning(
                        "Token metadata enrichment failed without invalidating receipt tx={} error_type={}",
                        tx_hash,
                        type(exc).__name__,
                    )
            decoded["rpc_retrieval"] = "success"
            return decoded
    except TransactionNotFound:
        raise HTTPException(status_code=404, detail="Transaction receipt not found")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Ethereum RPC timed out")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Transaction event lookup failed tx={} error_type={}", tx_hash, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Ethereum RPC receipt lookup failed")
