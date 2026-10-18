/** API client for the Blockchain Intelligence backend. */
const configuredBase = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
const API_BASE = configuredBase
  ? `${configuredBase}${configuredBase.endsWith('/api') ? '' : '/api'}`
  : '/api';

// Legacy tab credential helpers remain for the old hidden AnalystReviewPanel only.
// Case Management no longer uses browser storage for credentials.
function analystCredential() {
  return sessionStorage.getItem('chainscope_analyst_credential') || '';
}

export function setAnalystCredential(value) {
  const token = String(value || '').trim();
  if (token) sessionStorage.setItem('chainscope_analyst_credential', token);
  else sessionStorage.removeItem('chainscope_analyst_credential');
}

export function hasAnalystCredential() {
  return Boolean(analystCredential());
}

function authHeaders(headers = {}) {
  const credential = analystCredential();
  return credential ? { ...headers, Authorization: `Bearer ${credential}` } : headers;
}

async function request(path, timeoutMs = 12000, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
  if (!response.ok) {
    let detail = '';
    let payload = null;
    try {
      payload = await response.json();
      detail = typeof payload?.detail === 'string' ? payload.detail : '';
    } catch (parseError) {
      void parseError;
    }
    const error = new Error(detail || `API error: ${response.status} ${response.statusText}`);
    error.status = response.status;
    error.requestId = response.headers.get('x-request-id') || '';
    error.retryAfter = Number(response.headers.get('retry-after') || 0) || 0;
    error.rateLimit = Number(response.headers.get('x-ratelimit-limit') || 0) || 0;
    error.rateBucket = payload?.bucket || '';
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function jsonOptions(payload, privileged = false) {
  const headers = privileged ? authHeaders({ 'Content-Type': 'application/json' }) : { 'Content-Type': 'application/json' };
  return { method: 'POST', headers, body: JSON.stringify(payload) };
}

function viewerOptions(method = 'GET') {
  return { method, headers: authHeaders() };
}

let viewerSessionPromise = null;
async function ensureViewerSession() {
  if (analystCredential()) return;
  if (!viewerSessionPromise) {
    viewerSessionPromise = request('/session/viewer', 8000, { method: 'POST' })
      .catch(error => {
        viewerSessionPromise = null;
        throw error;
      });
  }
  await viewerSessionPromise;
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
  saveAnalystReview: (hash, payload) => request(`/analyst/transactions/${encodeURIComponent(hash)}`, 12000, jsonOptions(payload, true)),
  saveClusterReview: payload => request('/analyst/clusters/review', 30000, jsonOptions(payload, true)),
  recordAnalystEvent: (hash, payload) => request(`/analyst/transactions/${encodeURIComponent(hash)}/events`, 12000, jsonOptions(payload, true)),
  getAnalystAudit: (hash, limit = 100) => request(`/analyst/transactions/${encodeURIComponent(hash)}/audit?limit=${limit}`),
  getTransactionEvents: hash => request(`/transactions/${encodeURIComponent(hash)}/events`),
  getReceiptEvidence: hash => request(`/wallets/tx/${encodeURIComponent(hash)}/receipt-evidence`, 20000),
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
  getFundFlow: (address, depth = 3, limit = 300) => request(`/wallets/${encodeURIComponent(address)}/fund-flow?depth=${depth}&limit=${limit}&per_hop_limit=160`, 30000),
  getWalletReport: address => request(`/wallets/${encodeURIComponent(address)}/investigation-report?per_direction=50`, 30000),
  getWalletCoverageSummary: address => request(`/wallets/${encodeURIComponent(address)}/coverage-summary`, 15000),
  getCopilot: async address => {
    await ensureViewerSession();
    return request(`/wallets/${encodeURIComponent(address)}/copilot`, 30000, viewerOptions('POST'));
  },
  getAnalystSession: () => request('/session/analyst', 8000),
  createAnalystSession: accessKey => request('/session/analyst', 8000, jsonOptions({ access_key: accessKey })),
  clearAnalystSession: () => request('/session/analyst', 8000, { method: 'DELETE' }),
  listCases: (status = '') => request(`/analyst/cases${status ? `?status=${encodeURIComponent(status)}` : ''}`, 15000, viewerOptions()),
  getCase: caseId => request(`/analyst/cases/${encodeURIComponent(caseId)}`, 15000, viewerOptions()),
  createCase: payload => request('/analyst/cases', 15000, jsonOptions(payload, true)),
  addCaseItem: (caseId, payload) => request(`/analyst/cases/${encodeURIComponent(caseId)}/items`, 15000, jsonOptions(payload, true)),
  updateCase: (caseId, payload) => request(`/analyst/cases/${encodeURIComponent(caseId)}/state`, 15000, jsonOptions(payload, true)),
  getCaseReport: caseId => request(`/analyst/cases/${encodeURIComponent(caseId)}/report`, 20000, viewerOptions()),
  getCaseBundle: caseId => request(`/analyst/cases/${encodeURIComponent(caseId)}/bundle`, 25000, viewerOptions()),
};
