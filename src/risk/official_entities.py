"""High-confidence Ethereum entity registry sourced from first-party publications.

The registry deliberately favors provenance over breadth. Every row is an exact
Ethereum mainnet address published by the protocol or issuer itself. Labels are
address-level context only: they do not infer beneficial ownership, user identity,
intent, illegality, or transaction legitimacy.
"""
import json
from loguru import logger


OFFICIAL_ENTITY_RECORDS = (
    {"address": "0x000000000004444c5dc75cb358380d2e3de08a90", "source": "uniswap_official_ethereum_deployments", "entity_id": "uniswap-v4-pool-manager", "entity_name": "Uniswap v4 PoolManager", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    {"address": "0xbd216513d74c8cf14cf4747e6aaa6420ff64ee9e", "source": "uniswap_official_ethereum_deployments", "entity_id": "uniswap-v4-position-manager", "entity_name": "Uniswap v4 PositionManager", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    {"address": "0x000000000022d473030f116ddee9f6b43ac78ba3", "source": "uniswap_official_ethereum_deployments", "entity_id": "uniswap-permit2", "entity_name": "Uniswap Permit2", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    {"address": "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45", "source": "uniswap_official_ethereum_deployments", "entity_id": "uniswap-swap-router02", "entity_name": "Uniswap SwapRouter02", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    {"address": "0x66a9893cc07d91d95644aedd05d03f95e1dba8af", "source": "uniswap_official_ethereum_deployments", "entity_id": "uniswap-universal-router", "entity_name": "Uniswap UniversalRouter", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    {"address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "source": "uniswap_official_ethereum_deployments", "entity_id": "ethereum-weth9", "entity_name": "Wrapped Ether WETH9", "entity_type": "protocol", "confidence": 1.0, "source_url": "https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments", "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"}},
    # Uniswap — official deployment / SDK repositories.
    {
        "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-factory",
        "entity_name": "Uniswap V3 Factory",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xe592427a0aece92de3edee1f18e0157c05861564",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-swap-router",
        "entity_name": "Uniswap V3 SwapRouter",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xc36442b4a4522e871399cd717abdd847ab11fe88",
        "source": "uniswap_official_deployments",
        "entity_id": "uniswap-v3-position-manager",
        "entity_name": "Uniswap V3 NonfungiblePositionManager",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/deploys.md",
        "evidence": {"publisher": "Uniswap", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
        "source": "uniswap_official_sdk",
        "entity_id": "uniswap-v2-factory",
        "entity_name": "Uniswap V2 Factory",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/sdks/blob/main/sdks/sdk-core/src/addresses.ts",
        "evidence": {"publisher": "Uniswap", "method": "Ethereum mainnet constant in official SDK"},
    },
    {
        "address": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
        "source": "uniswap_official_sdk",
        "entity_id": "uniswap-v2-router02",
        "entity_name": "Uniswap V2 Router02",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/sdks/blob/main/sdks/sdk-core/src/addresses.ts",
        "evidence": {"publisher": "Uniswap", "method": "Ethereum mainnet constant in official SDK"},
    },
    {
        "address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
        "source": "uniswap_official_sdk",
        "entity_id": "uniswap-uni-token",
        "entity_name": "Uniswap UNI Token",
        "entity_type": "token",
        "confidence": 1.0,
        "source_url": "https://github.com/Uniswap/sdks/blob/main/sdks/sdk-core/src/addresses.ts",
        "evidence": {"publisher": "Uniswap", "method": "Ethereum token constant in official SDK"},
    },

    # Aave.
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

    # Lido — exact Ethereum mainnet contracts from official deployed-contracts documentation.
    {
        "address": "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",
        "source": "lido_official_docs",
        "entity_id": "lido-steth",
        "entity_name": "Lido stETH / Staking Pool",
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
        "address": "0xc1d0b3de6792bf6b4b37eccdcc24e45978cfd2eb",
        "source": "lido_official_docs",
        "entity_id": "lido-locator",
        "entity_name": "Lido Locator Proxy",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x23ed611be0e1a820978875c0122f92260804cddf",
        "source": "lido_official_docs",
        "entity_id": "lido-accounting",
        "entity_name": "Lido Accounting Proxy",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xa88f0329c2c4ce51ba3fc619bbf44efe7120dd0d",
        "source": "lido_official_docs",
        "entity_id": "lido-wsteth-referral-staker",
        "entity_name": "Lido wstETH Referral Staker",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x8f73e4c2a6d852bb4ab2a45e6a9cf5715b3228b7",
        "source": "lido_official_docs",
        "entity_id": "lido-eip712-helper",
        "entity_name": "Lido EIP-712 Helper",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xfddf38947afb03c621c71b06c9c70bce73f12999",
        "source": "lido_official_docs",
        "entity_id": "lido-staking-router",
        "entity_name": "Lido Staking Router Proxy",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xf98ac162eab766bdb9507c3584c00c535b8f6216",
        "source": "lido_official_docs",
        "entity_id": "lido-beacon-chain-depositor",
        "entity_name": "Lido Beacon Chain Depositor",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x39bb5d491e98a44d1bfe8047a737a81e296a63e0",
        "source": "lido_official_docs",
        "entity_id": "lido-deposit-security-module",
        "entity_name": "Lido Deposit Security Module",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x388c818ca8b9251b393131c08a736a67ccb19297",
        "source": "lido_official_docs",
        "entity_id": "lido-execution-layer-rewards-vault",
        "entity_name": "Lido Execution Layer Rewards Vault",
        "entity_type": "infrastructure",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0x889edc2edab5f40e902b864ad4d7ade8e412f9b1",
        "source": "lido_official_docs",
        "entity_id": "lido-withdrawal-queue",
        "entity_name": "Lido Withdrawal Queue ERC721 Proxy",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },
    {
        "address": "0xb9d7934878b5fb9610b3fe8a5e441e8fad7e293f",
        "source": "lido_official_docs",
        "entity_id": "lido-withdrawal-vault",
        "entity_name": "Lido Withdrawal Vault Proxy",
        "entity_type": "protocol",
        "confidence": 1.0,
        "source_url": "https://docs.lido.fi/deployed-contracts/",
        "evidence": {"publisher": "Lido", "method": "exact Ethereum mainnet deployment address"},
    },

    # Stablecoin / token issuers and oracle infrastructure.
    {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "source": "circle_official_usdc",
        "entity_id": "circle-usdc-ethereum",
        "entity_name": "USDC on Ethereum",
        "entity_type": "token",
        "confidence": 1.0,
        "source_url": "https://www.circle.com/multi-chain-usdc/ethereum",
        "evidence": {"publisher": "Circle", "method": "native USDC Ethereum mainnet contract address"},
    },
    {
        "address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "source": "tether_official_protocols",
        "entity_id": "tether-usdt-ethereum",
        "entity_name": "Tether USD₮ on Ethereum",
        "entity_type": "token",
        "confidence": 1.0,
        "source_url": "https://tether.to/en/supported-protocols/",
        "evidence": {"publisher": "Tether", "method": "official Ethereum USD₮ contract address"},
    },
    {
        "address": "0x514910771af9ca656af840dff83e8264ecf986ca",
        "source": "chainlink_official_docs",
        "entity_id": "chainlink-link-token-ethereum",
        "entity_name": "Chainlink LINK Token on Ethereum",
        "entity_type": "token",
        "confidence": 1.0,
        "source_url": "https://docs.chain.link/resources/link-token-contracts",
        "evidence": {"publisher": "Chainlink", "method": "official Ethereum mainnet LINK token contract"},
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
