/**
 * API client for the Blockchain Intelligence backend.
 * Uses VITE_API_URL env var in production, falls back to /api in dev.
 */

const API_BASE = import.meta.env.VITE_API_URL 
  ? `${import.meta.env.VITE_API_URL}/api`
  : '/api';

async function request(path) {
  const response = await fetch(`${API_BASE}${path}`);
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
};