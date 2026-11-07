import { useState } from 'react';
import { bestAddressLabel } from '../utils/knownContracts';

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return { text: '0 ETH · possible contract call', title: 'No native ETH transferred; token activity requires event evidence' };
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    const text = `${whole}${fraction ? `.${fraction.slice(0, 6)}` : ''} ETH`;
    return { text, title: text };
  }
  if (tx.value_eth == null || tx.value_eth === '') return { text: 'Value unavailable', title: 'No native-ETH value supplied by the data source' };
  const value = Number(tx.value_eth);
  if (!Number.isFinite(value)) return { text: 'Value unavailable', title: 'Invalid native-ETH value supplied by the data source' };
  if (value === 0) return { text: '0 ETH · possible contract call', title: 'No native ETH transferred; token activity requires event evidence' };
  const text = `${value.toPrecision(6)} ETH`;
  return { text, title: text };
}

function riskMeta(score) {
  if (score >= 80) return { label: 'Critical', cls: 'border-red-500/35 bg-red-500/10 text-red-300', symbol: '●' };
  if (score >= 40) return { label: 'High review', cls: 'border-orange-500/35 bg-orange-500/10 text-orange-300', symbol: '▲' };
  if (score >= 20) return { label: 'Review', cls: 'border-yellow-500/35 bg-yellow-500/10 text-yellow-200', symbol: '◆' };
  if (score > 0) return { label: 'Low signal', cls: 'border-emerald-500/25 bg-emerald-500/[0.07] text-emerald-300', symbol: '○' };
  return { label: 'No signal', cls: 'border-slate-600 bg-slate-800/50 text-slate-400', symbol: '—' };
}

function shortHash(value) {
  if (!value) return 'N/A';
  return value.length <= 21 ? value : `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function shortAddress(value) {
  if (!value) return 'N/A';
  return value.length <= 17 ? value : `${value.slice(0, 8)}…${value.slice(-6)}`;
}

function parseUtc(timestamp) {
  if (!timestamp) return null;
  const raw = String(timestamp);
  const explicit = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(explicit);
  return Number.isNaN(date.getTime()) ? null : date;
}

function timeLabel(timestamp) {
  const date = parseUtc(timestamp);
  if (!date) return 'Unknown time';
  return `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

function factorReason(tx) {
  const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors : [];
  const first = factors.find(item => item && typeof item === 'object');
  const named = factors.map(item => item?.factor || item?.name).filter(Boolean).filter(name => name !== 'bursty_activity');
  const labels = { whale_transaction: 'Whale-sized ETH', large_transaction: 'Large ETH transfer', notable_transaction: 'Notable ETH transfer', medium_transaction: 'ETH value', ping_pong_pattern: 'Bidirectional repeats', repeated_counterparty: 'Counterparty concentration', new_wallet: 'Recently first-observed wallet', unusual_value: 'Unusual transfer size', zero_value: 'Contract call / zero ETH', blacklisted_address: 'Verified blocklist match' };
  if (named.length) return named.slice(0, 2).map(name => labels[name] || name.replaceAll('_', ' ')).join(' + ');
  if (first?.factor === 'bursty_activity') return `Velocity: ${Number(first.observed_transfer_count || 0)} transfers / ${Number(first.window_minutes || 60)}m`;
  return first?.reason || first?.name || first?.type || null;
}

function AddressCell({ address, matches = [] }) {
  const label = bestAddressLabel(address, matches);
  return <div className="min-w-0"><div className="font-mono text-xs text-slate-300" title={address}>{shortAddress(address)}</div>{address && <a href={`https://etherscan.io/address/${encodeURIComponent(address)}`} target="_blank" rel="noopener noreferrer" className="text-[10px] text-sky-400 underline-offset-2 hover:underline" aria-label={`Inspect ${address} on Etherscan`}>Explorer ↗</a>}{label && <div className="mt-1 max-w-[180px] truncate text-xs font-medium text-sky-300" title={`${label.label} · ${label.type}`}>{label.label} · {label.type}</div>}</div>;
}

function SortHeader({ label, field, sort, onSort, className = '' }) {
  const desc = `${field}_desc`;
  const asc = `${field}_asc`;
  const active = sort === desc || sort === asc;
  const next = sort === desc ? asc : desc;
  return <th scope="col" className={`px-4 py-3 ${className}`}><button type="button" onClick={() => onSort(next)} className="inline-flex min-h-11 items-center gap-1 hover:text-sky-300">{label}<span aria-hidden="true">{active ? (sort === desc ? '↓' : '↑') : '↕'}</span></button></th>;
}

export default function TransactionList({ transactions = [], onSelect, totalMatches = 0, loading = false, error = null, onRetry, offset = 0, sort = 'risk_desc', onSort = () => {}, freshness = 'unknown' }) {
  const [openScore, setOpenScore] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const shown = transactions.length;
  const total = Number(totalMatches || 0);
  const start = shown ? Number(offset) + 1 : 0;
  const end = shown ? Number(offset) + shown : 0;

  return <section className="transaction-panel" aria-labelledby="transactions-heading">
    <div className="transaction-panel-head"><div><span className="cs-section-kicker">02 / EVIDENCE LEDGER</span><h2 id="transactions-heading" className="text-lg font-semibold text-white">Transactions</h2><p className="mt-1 text-sm text-slate-400">Showing {start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()} matching records</p></div><span className="hidden text-sm text-slate-400 sm:inline">Select a record for its source evidence</span></div>

    {loading && <div className="space-y-3 p-6" aria-live="polite" aria-label="Loading transactions">{[0,1,2,3].map(i => <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-800/70" />)}</div>}
    {!loading && error && <div className="py-14 text-center"><p className="text-sm text-rose-300">{error}</p>{onRetry && <button type="button" onClick={onRetry} className="workspace-chip mt-4">Retry</button>}</div>}
    {!loading && !error && !shown && <div className="py-14 px-5 text-center text-sm text-slate-400"><p>No transactions match the active filters.</p><p className="mt-2 text-xs">{freshness === 'live' ? 'Try clearing filters. This view covers only retained indexed records.' : 'Indexer freshness is unverified or delayed; this does not mean Ethereum has no activity.'}</p></div>}

    {!loading && !error && shown > 0 && <>
      <div className="cs-transaction-scroll hidden xl:block" role="region" aria-label="Transactions table" tabIndex={0}>
        <table className="cs-transaction-table w-full border-collapse text-left text-sm">
          <thead>
            <tr>
              <SortHeader label="Time" field="time" sort={sort === 'newest' ? 'time_desc' : sort === 'oldest' ? 'time_asc' : sort} onSort={value => onSort(value === 'time_desc' ? 'newest' : 'oldest')} />
              <th scope="col">Transaction</th>
              <th scope="col">Transfer path</th>
              <SortHeader label="Amount" field="value" sort={sort} onSort={onSort} />
              <SortHeader label="Review score" field="risk" sort={sort} onSort={onSort} />
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map(tx => {
              const score = Number(tx.risk_score) || 0;
              const risk = riskMeta(score);
              const amount = formatEth(tx);
              const reason = factorReason(tx);
              return <tr key={tx.hash} className="cs-ledger-row">
                <td className="cs-transaction-time" title={timeLabel(tx.timestamp)}>{timeLabel(tx.timestamp)}</td>
                <td className="cs-transaction-hash" title={tx.hash}>
                  <span className="font-mono text-xs">{shortHash(tx.hash)}</span>
                  <button type="button" className="cs-transaction-link text-left" aria-expanded={expandedRow === tx.hash} onClick={() => setExpandedRow(expandedRow === tx.hash ? null : tx.hash)}>{expandedRow === tx.hash ? 'Hide context −' : 'Show context +'}</button>
                  {expandedRow === tx.hash && <div className="cs-inline-evidence"><p>Block {tx.block_number ?? '—'} · {tx.hash}</p><a href={`https://etherscan.io/tx/${encodeURIComponent(tx.hash)}`} target="_blank" rel="noopener noreferrer" aria-label={`Inspect transaction ${tx.hash} on Etherscan`}>Verify on Etherscan ↗</a></div>}
                </td>
                <td className="cs-transaction-path">
                  <div className="cs-path-pair">
                    <span className="cs-path-direction">From</span>
                    <AddressCell address={tx.from_address} matches={tx.entity_context?.sender} />
                    <span className="cs-path-arrow" aria-hidden="true">→</span>
                    <span className="cs-path-direction">To</span>
                    <AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} />
                  </div>
                </td>
                <td className="cs-transaction-value" title={amount.title}>{amount.text}</td>
                <td className="cs-transaction-risk">
                  <button type="button" aria-expanded={openScore === tx.hash} onClick={() => setOpenScore(openScore === tx.hash ? null : tx.hash)} className={`cs-score-button inline-flex items-center rounded border px-2 py-1.5 text-xs font-semibold ${risk.cls}`} title="Show recorded score factors">{risk.label} · {score} <span aria-hidden="true">{openScore === tx.hash ? '▴' : '▾'}</span></button>
                  {openScore === tx.hash && <p className="cs-signal-summary" title={reason || 'No recorded signal'}>{reason || 'No recorded signal'}</p>}
                  {openScore === tx.hash && <div className="cs-factor-popout text-xs text-slate-300">{Array.isArray(tx.risk_factors) && tx.risk_factors.length ? tx.risk_factors.map((factor, i) => <div key={i}>+{Number(factor.points) || 0}: {factor.reason || factor.factor || 'Recorded signal'}</div>) : 'No recorded score factors'}<p className="mt-2">Review score {score}/100 — not a fraud probability.</p></div>}
                </td>
                <td className="cs-transaction-action"><button type="button" onClick={() => onSelect(tx)} className="workspace-chip cs-details-button">View details <span aria-hidden="true">↗</span></button></td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>

      <div className="cs-transaction-mobile divide-y divide-[#39475d] xl:hidden">{transactions.map(tx => {
        const score = Number(tx.risk_score) || 0;
        const risk = riskMeta(score);
        const amount = formatEth(tx);
        return <article key={tx.hash} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="break-all font-mono text-sm text-slate-200">{shortHash(tx.hash)}</p><p className="mt-1 text-xs text-slate-300">{timeLabel(tx.timestamp)}</p></div><span className={`shrink-0 rounded border px-2 py-1 text-xs ${risk.cls}`}>{risk.label}{score ? ` · ${score}` : ''}</span></div><div className="grid grid-cols-[56px_minmax(0,1fr)] gap-2 text-sm"><span className="text-slate-300">From</span><AddressCell address={tx.from_address} matches={tx.entity_context?.sender} /><span className="text-slate-300">To</span><AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} /><span className="text-slate-300">Value</span><span className="text-white">{amount.text}</span></div><button type="button" onClick={() => onSelect(tx)} className="workspace-chip w-full">View details</button></article>;
      })}</div>
    </>}
  </section>;
}
