const KNOWN_CONTRACTS = {
  '0xdac17f958d2ee523a2206206994597c13d831ec7': { label: 'USDT', type: 'ERC-20 token contract' },
  '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': { label: 'USDC', type: 'ERC-20 token contract' },
  '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': { label: 'WETH', type: 'Wrapped Ether contract' },
  '0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789': { label: 'EntryPoint v0.6', type: 'ERC-4337 infrastructure' },
  '0x0000000071727de22e5e9d8baf0edac6f37da032': { label: 'EntryPoint v0.7', type: 'ERC-4337 infrastructure' },
};

export function knownContract(address) {
  if (!address) return null;
  return KNOWN_CONTRACTS[String(address).toLowerCase()] || null;
}

export function bestAddressLabel(address, entityMatches = []) {
  const verified = Array.isArray(entityMatches)
    ? entityMatches.find(item => item?.entity_name || item?.entity_id)
    : null;
  if (verified) {
    return {
      label: verified.entity_name || verified.entity_id,
      type: verified.entity_type || 'source-attributed entity',
      source: verified.source || null,
      verified: true,
    };
  }
  const known = knownContract(address);
  return known ? { ...known, source: 'canonical contract registry', verified: true } : null;
}
