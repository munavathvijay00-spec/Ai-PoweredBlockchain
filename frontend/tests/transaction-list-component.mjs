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
    onSelect: () => {},
  }));
  assert.match(empty, /No transactions match the active filters/);
  assert.doesNotMatch(empty, /Confirm Risk|False Positive|Escalate|Analyst identity/);

  const tx = {
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
    ],
  };

  const rendered = renderToStaticMarkup(React.createElement(TransactionList, {
    transactions: [tx], totalMatches: 1,
    loading: false, error: null, onSelect: () => {}, onSort: () => {},
  }));
  assert.match(rendered, /Transactions/);
  assert.match(rendered, /High review/);
  assert.match(rendered, /Large ETH transfer/);
  assert.match(rendered, /65/);
  assert.match(rendered, /Show recorded score factors/);
  assert.match(rendered, /etherscan\\.io\\/address/);
  assert.match(rendered, /View details/);
  assert.doesNotMatch(rendered, /Confirm Risk|False Positive|Needs Review|Escalate|Export evidence/);

  const failed = renderToStaticMarkup(React.createElement(TransactionList, {
    transactions: [], totalMatches: 0, loading: false,
    error: 'upstream node timeout', onRetry: () => {}, onSelect: () => {}, onSort: () => {},
  }));
  assert.match(failed, /upstream node timeout/);
  assert.match(failed, /Retry/);

  console.log('TransactionList component render checks passed.');
} finally {
  await vite.close();
}
