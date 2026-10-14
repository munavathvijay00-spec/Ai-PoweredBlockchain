"""Small, high-confidence registry sourced from first-party protocol documentation.

This registry deliberately favors provenance over breadth. Each row is an exact
Ethereum mainnet contract address published by the protocol or issuer's own
documentation/repository. These labels provide address-level context only; they do
not infer beneficial ownership, user identity, intent, or transaction legitimacy.
"""
import json
from loguru import logger


OFFICIAL_ENTITY_RECORDS = (
    {
        "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-factory",
        "entity_name": "Uniswap V3 Factory",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact mainnet deployment address"},
    },
    {
        "address": "0xe592427a0aece92de3edee1f18e0157c05861564",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-swap-router",
        "entity_name": "Uniswap V3 SwapRouter",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact mainnet deployment address"},
    },
    {
        "address": "0xc36442b4a4522e871399cd717abdd847ab11fe88",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-position-manager",
        "entity_name": "Uniswap V3 NonfungiblePositionManager",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact mainnet deployment address"},
    },
    {
        "address": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
        "source": "aave_official_docs",
        "entity_id": "aave-v3-ethereum-market",
        "entity_name": "Aave V3 Ethereum Market",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://aave.com/docs/aave-v3/markets/data",
        "evidence": {"publisher": "Aave", "method": "exact Ethereum market address in official docs"},
    },
    {
        "address": "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",
        "source": "lido_official_docs",
        "entity_id": "lido-steth",
        "entity_name": "Lido stETH / staking pool",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",
        "source": "lido_official_docs",
        "entity_id": "lido-wsteth",
        "entity_name": "Lido wstETH",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "source": "circle_official_usdc",
        "entity_id": "circle-usdc-ethereum",
        "entity_name": "USDC on Ethereum",
        "entity_type": "contract",
        "confidence": 1.0,
        "source_url": "https://www.circle.com/multi-chain-usdc/ethereum",
        "evidence": {"publisher": "Circle", "method": "native USDC Ethereum mainnet contract address"},
    },
)


async def sync_official_entities(db) -> int:
    """Upsert the bounded first-party registry into entity_attributions."""
    has_table = await db.fetchval("SELECT to_regclass('entity_attributions') IS NOT NULL")
    if not has_table:
        logger.warning("Official entity registry skipped: entity_attributions schema unavailable")
        return 0

    for row in OFFICIAL_ENTITY_RECORDS:
        await db.execute(
            """
            INSERT INTO entity_attributions (
                chain_id,address,source,entity_id,entity_name,entity_type,
                confidence,attribution_scope,source_url,evidence,verified_at
            ) VALUES (1,$1,$2,$3,$4,$5,$6,'address',$7,$8::jsonb,NOW())
            ON CONFLICT (chain_id,address,source,entity_id) DO UPDATE SET
                entity_name=EXCLUDED.entity_name,
                entity_type=EXCLUDED.entity_type,
                confidence=EXCLUDED.confidence,
                attribution_scope='address',
                source_url=EXCLUDED.source_url,
                evidence=EXCLUDED.evidence,
                verified_at=NOW(),
                expires_at=NULL
            """,
            row["address"], row["source"], row["entity_id"], row["entity_name"],
            row["entity_type"], row["confidence"], row["source_url"],
            json.dumps(row["evidence"]),
        )

    logger.info("Verified entity registry: synced {} first-party addresses", len(OFFICIAL_ENTITY_RECORDS))
    return len(OFFICIAL_ENTITY_RECORDS)
