/**
 * API client for the Blockchain Intelligence backend.
 * Uses VITE_API_URL env var in production, falls back to /api in dev.
 */

const configuredBase = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
const API_BASE = configuredBase
  ? `${configuredBase}${configuredBase.endsWith('/api') ? '' : '/api'}`
  : '/api';

async function request(path, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export const api = {
  getStats: () => request('/stats'),
  getCoverage: () => request('/coverage'),
  getTransactions: (limit = 50) => request(`/transactions?limit=${limit}`),
  getFlagged: (limit = 50, minScore = 20) => request(`/flagged?min_score=${minScore}&limit=${limit}`),
  getTransaction: (hash) => request(`/transactions/${hash}`),
  getTransactionEvents: (hash) => request(`/transactions/${encodeURIComponent(hash)}/events`),
  getWalletBalance: address => request(`/wallets/${encodeURIComponent(address)}/balance`),
  getWalletTransfers: (address, cursors = {}, directions = { outgoing: true, incoming: true }) => {
    const params = new URLSearchParams({ per_direction: '25' });
    params.set('include_outgoing', String(directions.outgoing));
    params.set('include_incoming', String(directions.incoming));
    if (cursors.outgoing_page_key) params.set('outgoing_page_key', cursors.outgoing_page_key);
    if (cursors.incoming_page_key) params.set('incoming_page_key', cursors.incoming_page_key);
    return request(`/wallets/${encodeURIComponent(address)}/transfers?${params}`, 25000);
  },
  getWalletGraph: (address, cursors = {}) => {
    const params = new URLSearchParams({ per_direction: '25' });
    if (cursors.outgoing) params.set('outgoing_page_key', cursors.outgoing);
    if (cursors.incoming) params.set('incoming_page_key', cursors.incoming);
    return request(`/wallets/${encodeURIComponent(address)}/indexed-graph?${params}`, 25000);
  },
  getWalletReport: address => request(`/wallets/${encodeURIComponent(address)}/investigation-report`, 25000),
};
