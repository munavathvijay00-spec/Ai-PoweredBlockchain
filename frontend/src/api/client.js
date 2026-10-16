/** API client for the Blockchain Intelligence backend. */
const configuredBase = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
const API_BASE = configuredBase
  ? `${configuredBase}${configuredBase.endsWith('/api') ? '' : '/api'}`
  : '/api';

async function request(path, timeoutMs = 12000, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { signal: controller.signal, ...options });
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = typeof payload?.detail === 'string' ? payload.detail : '';
    } catch {
      // Keep the HTTP fallback for non-JSON upstream failures.
    }
    throw new Error(detail || `API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

function jsonOptions(payload) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}

function browserParams(options = {}) {
  const params = new URLSearchParams();
  const allowed = ['limit', 'offset', 'search', 'min_risk', 'max_risk', 'min_value_eth', 'max_value_eth', 'sort', 'clustered'];
  allowed.forEach(key => {
    const value = options[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') params.set(key, String(value));
  });
  return params;
}

function addressParams(options = {}) {
  const params = new URLSearchParams();
  ['limit', 'offset', 'search', 'sort'].forEach(key => {
    const value = options[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') params.set(key, String(value));
  });
  return params;
}

export const api = {
  getStats: () => request('/stats'),
  getCoverage: () => request('/coverage'),
  getAIStatus: () => request('/ai/status'),
  getMLStatus: () => request('/ml/status'),
  getExternalEvaluation: () => request('/evaluation/external', 20000),
  getTransactions: (limit = 50, offset = 0) => request(`/transactions?limit=${limit}&offset=${offset}`),
  getFlagged: (limit = 50, minScore = 20) => request(`/flagged?min_score=${minScore}&limit=${limit}`),
  getTransactionBrowser: options => request(`/transaction-browser?${browserParams({ clustered: true, ...options })}`, 20000),
  getTransactionExportUrl: (format = 'csv', options = {}) => {
    const params = browserParams(options);
    params.delete('clustered');
    params.set('format', format);
    return `${API_BASE}/transaction-export?${params}`;
  },
  getAddressBrowser: options => request(`/address-browser?${addressParams(options)}`, 20000),
  getTransaction: hash => request(`/transactions/${encodeURIComponent(hash)}`),
  getAnalystReview: hash => request(`/analyst/transactions/${encodeURIComponent(hash)}`),
  saveAnalystReview: (hash, payload) => request(`/analyst/transactions/${encodeURIComponent(hash)}`, 12000, jsonOptions(payload)),
  saveClusterReview: payload => request('/analyst/clusters/review', 30000, jsonOptions(payload)),
  recordAnalystEvent: (hash, payload) => request(`/analyst/transactions/${encodeURIComponent(hash)}/events`, 12000, jsonOptions(payload)),
  getAnalystAudit: (hash, limit = 100) => request(`/analyst/transactions/${encodeURIComponent(hash)}/audit?limit=${limit}`),
  getTransactionEvents: hash => request(`/transactions/${encodeURIComponent(hash)}/events`),
  getWalletBalance: address => request(`/wallets/${encodeURIComponent(address)}/balance`, 15000),
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
  getObservedWalletGraph: (address, depth = 2, limit = 150) => {
    const params = new URLSearchParams({ depth: String(depth), limit: String(limit), per_hop_limit: '120' });
    return request(`/wallets/${encodeURIComponent(address)}/graph?${params}`, 25000);
  },
  getWalletReport: address => request(`/wallets/${encodeURIComponent(address)}/investigation-report`, 25000),
};
