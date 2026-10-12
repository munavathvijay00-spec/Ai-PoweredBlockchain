/**
 * API client for the Blockchain Intelligence backend.
 * Uses VITE_API_URL env var in production, falls back to /api in dev.
 */

const configuredBase = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
const API_BASE = configuredBase
  ? `${configuredBase}${configuredBase.endsWith('/api') ? '' : '/api'}`
  : '/api';

async function request(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
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
  getTransactions: (limit = 50) => request(`/transactions?limit=${limit}`),
  getFlagged: (minScore = 20) => request(`/flagged?min_score=${minScore}`),
  getTransaction: (hash) => request(`/transactions/${hash}`),
  getTransactionEvents: (hash) => request(`/transactions/${encodeURIComponent(hash)}/events`),
};