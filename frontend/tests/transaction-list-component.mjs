import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';

globalThis.localStorage = {
  values: new Map(),
  getItem(key) { return this.values.get(key) || null; },
  setItem(key, value) { this.values.set(key, String(value)); },
};

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: TransactionList } = await vite.ssrLoadModule('/src/components/TransactionList.jsx');

  const empty = renderToStaticMarkup(React.createElement(TransactionList, {
    transactions: [], totalMatches: 0, loading: false, error: null,
    onSelect: () => {}, onClearFilters: () => {},
  }));
  assert.match(empty, /No transactions match the active filters/);
  assert.match(empty, /Clear filters/);

  const clustered = renderToStaticMarkup(React.createElement(TransactionList, {
    transactions: [{
      hash: '0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      from_address: '0x1111111111111111111111111111111111111111',
      to_address: '0x2222222222222222222222222222222222222222',
      value_wei: '100000000000000000000',
      block_number: 1,
      timestamp: '2026-10-16T00:00:00Z',
      risk_score: 65,
      risk_factors: [
        { factor: 'large_transaction', points: 30, reason: '100 ETH transfer', observed_value_wei: '100000000000000000000' },
        { factor: 'bursty_activity', points: 25, reason: '11 observed transfers in 60 minutes', observed_transfer_count: 11, window_minutes: 60 },
        { factor: 'repeated_counterparty', points: 10, reason: 'Repeated counterparty', observed_transfer_count: 6 },
      ],
      cluster: {
        count: 11,
        hashes: Array.from({ length: 11 }, (_, i) => `0x${String(i).padStart(64, '0')}`),
        oldest_timestamp: '2026-10-15T23:00:00Z',
        newest_timestamp: '2026-10-16T00:00:00Z',
        distinct_blocks: 4,
      },
    }],
    totalMatches: 1,
    matchingTransactions: 11,
    loading: false,
    error: null,
    onSelect: () => {},
    onSort: () => {},
  }));

  assert.match(clustered, /Clustered Review Queue/);
  assert.match(clustered, /11 tx/);
  assert.match(clustered, /Why flagged/);
  assert.match(clustered, /High review/);
  assert.match(clustered, /Confirm Risk/);
  assert.match(clustered, /False Positive/);
  assert.match(clustered, /Needs Review/);
  assert.match(clustered, /Escalate/);
  assert.match(clustered, /Export evidence/);

  console.log('TransactionList component render checks passed.');
} finally {
  await vite.close();
}
