import { useMemo, useState } from 'react';
import { api } from '../api/client';
import { bestAddressLabel } from '../utils/knownContracts';

const FACTOR_RULES = {
  blacklisted_address: 'Verified blocked-address interaction → +100',
  whale_transaction: 'Native transfer ≥ 1,000 ETH → +40',
  large_transaction: 'Native transfer ≥ 100 ETH → +30',
  notable_transaction: 'Native transfer ≥ 10 ETH → +20',
  medium_transaction: 'Native transfer ≥ 1 ETH → +10',
  bursty_activity: 'More than configured transfer threshold inside retained 60-minute window → +25',
  ping_pong_pattern: 'Repeated bidirectional transfers with direction changes → +20',
  repeated_counterparty: 'At least 6 recent interactions with one counterparty → +10',
  new_wallet: 'Wallet first observed inside configured new-wallet window → +15',
  unusual_value: 'Transfer exceeds 5× retained outgoing average → +10',
  zero_value: 'Zero native-ETH value transaction / contract-call signal → +5',
};

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return { text: '—', title: '0 ETH' };
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    const text = `${whole}${fraction ? `.${fraction.slice(0, 6)}` : ''} ETH`;
    return { text, title: text };
  }
  const value = Number(tx.value_eth);
  if (!Number.isFinite(value)) return { text: '—', title: 'Amount unavailable' };
  if (value === 0) return { text: '—', title: '0 ETH' };
  const text = `${value.toPrecision(6)} ETH`;
  return { text, title: text };
}

function riskMeta(score) {
  if (score >= 80) return { label: 'Critical', cls: 'border-red-500/40 bg-red-500/10 text-red-200', symbol: '●' };
  if (score >= 40) return { label: 'High review', cls: 'border-orange-500/40 bg-orange-500/10 text-orange-200', symbol: '▲' };
  if (score >= 20) return { label: 'Review', cls: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-100', symbol: '◆' };
  if (score > 0) return { label: 'Low signal', cls: 'border-emerald-500/35 bg-emerald-500/[0.07] text-emerald-200', symbol: '○' };
  return { label: 'No signal', cls: 'border-slate-600 bg-slate-800/50 text-slate-300', symbol: '—' };
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
  return date ? `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC` : 'Unknown time';
}

function durationLabel(start, end) {
  const a = parseUtc(start);
  const b = parseUtc(end);
  if (!a || !b) return 'retained window';
  const minutes = Math.max(0, Math.round((b - a) / 60000));
  if (minutes < 60) return `${minutes || 1} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} hr` : `${Math.round(hours / 24)} d`;
}

function riskFactors(tx) {
  return (Array.isArray(tx.risk_factors) ? tx.risk_factors : [])
    .filter(item => item && typeof item === 'object')
    .map((item, index) => ({
      ...item,
      factor: item.factor || item.name || item.type || `factor_${index + 1}`,
      points: Number(item.points || 0),
      reason: item.reason || item.name || item.type || 'Recorded risk factor',
    }));
}

function evidenceEntries(factor) {
  const hidden = new Set(['factor', 'name', 'type', 'points', 'reason', 'source']);
  return Object.entries(factor).filter(([key, value]) => !hidden.has(key) && value !== null && value !== undefined && value !== '');
}

function AddressCell({ address, matches = [] }) {
  const label = bestAddressLabel(address, matches);
  return <div className="min-w-0">
    <div className="font-mono text-xs text-slate-200" title={address}>{shortAddress(address)}</div>
    {label && <div className="mt-1 max-w-[180px] truncate text-[10px] font-medium text-sky-200" title={`${label.label} · ${label.type}`}>{label.label} · {label.type}</div>}
  </div>;
}

function SortHeader({ label, field, sort, onSort, className = '' }) {
  const desc = `${field}_desc`;
  const asc = `${field}_asc`;
  const active = sort === desc || sort === asc;
  const next = sort === desc ? asc : desc;
  const ariaSort = sort === desc ? 'descending' : sort === asc ? 'ascending' : 'none';
  return <th scope="col" aria-sort={ariaSort} className={`px-4 py-3 ${className}`}>
    <button type="button" onClick={() => onSort(next)} className="inline-flex items-center gap-1 rounded focus:outline-none focus:ring-2 focus:ring-sky-300">
      {label}<span aria-hidden="true">{active ? (sort === desc ? '↓' : '↑') : '↕'}</span>
    </button>
  </th>;
}

function FactorBreakdown({ tx, onAudit }) {
  const factors = riskFactors(tx);
  const score = Number(tx.risk_score) || 0;
  const raw = factors.reduce((sum, factor) => sum + Math.max(0, factor.points), 0);
  if (!factors.length) return <span className="text-xs text-slate-400">No recorded review factor</span>;

  return <details className="group max-w-[330px]">
    <summary className="cursor-pointer list-none rounded text-xs font-semibold text-sky-200 focus:outline-none focus:ring-2 focus:ring-sky-300">
      Why flagged <span className="text-slate-300">({score})</span> <span aria-hidden="true" className="text-slate-500 group-open:hidden">▸</span><span aria-hidden="true" className="hidden text-slate-500 group-open:inline">▾</span>
    </summary>
    <div className="mt-2 space-y-2 rounded-lg border border-[#405069] bg-[#0b1526] p-3">
      {factors.map((factor, index) => <details key={`${factor.factor}-${index}`} onToggle={event => {
        if (event.currentTarget.open) onAudit?.('view_rule', `Viewed rule ${factor.factor}`);
      }} className="rounded border border-slate-700/80 bg-slate-900/40 p-2">
        <summary className="flex cursor-pointer list-none items-start justify-between gap-3 text-[11px] text-slate-200">
          <span>{factor.reason}</span><strong className="whitespace-nowrap text-amber-200">+{factor.points}</strong>
        </summary>
        <div className="mt-2 border-t border-slate-700 pt-2 text-[10px] leading-5 text-slate-300">
          <p><span className="font-semibold text-slate-100">Rule:</span> {FACTOR_RULES[factor.factor] || 'Server-recorded evidence rule'}</p>
          {factor.source && <p><span className="font-semibold text-slate-100">Source:</span> {String(factor.source)}</p>}
          {evidenceEntries(factor).map(([key, value]) => <p key={key}><span className="font-semibold text-slate-100">{key.replaceAll('_', ' ')}:</span> {String(value)}</p>)}
        </div>
      </details>)}
      <div className="flex justify-between border-t border-slate-700 pt-2 text-[11px] font-semibold text-slate-100">
        <span>{raw > 100 ? `Raw ${raw} · capped at` : 'Total'}</span><span>{score}</span>
      </div>
    </div>
  </details>;
}

function ClusterSummary({ tx, onSelect }) {
  const count = Number(tx.cluster?.count || 1);
  if (count <= 1) return <span className="text-xs text-slate-500">Single transfer</span>;
  const hashes = Array.isArray(tx.cluster?.hashes) ? tx.cluster.hashes : [];
  return <details className="mt-2 text-xs">
    <summary className="cursor-pointer rounded font-semibold text-sky-200 focus:outline-none focus:ring-2 focus:ring-sky-300">Expand {count.toLocaleString()} transfers</summary>
    <div className="mt-2 max-h-44 overflow-auto rounded border border-slate-700 bg-slate-950/50 p-2" aria-label={`${count} transfer hashes in cluster`}>
      {hashes.map((hash, index) => <button key={hash} type="button" onClick={async () => {
        try { onSelect(await api.getTransaction(hash)); } catch { /* representative remains accessible */ }
      }} className="block w-full truncate rounded px-2 py-1 text-left font-mono text-[10px] text-slate-300 hover:bg-white/5 focus:outline-none focus:ring-2 focus:ring-sky-300" title={hash}>{index + 1}. {hash}</button>)}
    </div>
  </details>;
}

function ReviewActions({ tx, actor, onChanged, onMessage }) {
  const [busy, setBusy] = useState(false);
  const hashes = useMemo(() => {
    const clustered = Array.isArray(tx.cluster?.hashes) ? tx.cluster.hashes : [];
    return clustered.length ? clustered : [tx.hash];
  }, [tx]);

  async function review(status) {
    const labels = { confirmed: 'Confirm Risk', false_positive: 'False Positive', needs_review: 'Needs Review', escalated: 'Escalate' };
    let assignee = null;
    if (status === 'escalated') {
      assignee = window.prompt('Assign escalation to analyst / team:')?.trim();
      if (!assignee) return;
    }
    const note = window.prompt(`Reason for “${labels[status]}” (stored in audit log):`)?.trim();
    if (!note) return;
    setBusy(true);
    try {
      await api.saveClusterReview({ hashes, status, actor, assignee, note });
      onMessage(`${labels[status]} saved for ${hashes.length} transaction${hashes.length === 1 ? '' : 's'}.`);
      onChanged?.();
    } catch (error) {
      onMessage(error?.message || 'Unable to save analyst action.', true);
    } finally { setBusy(false); }
  }

  async function exportEvidence() {
    setBusy(true);
    try {
      await api.recordAnalystEvent(tx.hash, {
        action: 'export_evidence', actor,
        note: `Exported cluster evidence representing ${hashes.length} retained transaction(s).`,
      });
      const payload = {
        schema: 'chainscope-review-evidence/v1', exported_at: new Date().toISOString(), actor,
        representative_hash: tx.hash, cluster_hashes: hashes, cluster: tx.cluster || null,
        from_address: tx.from_address, to_address: tx.to_address,
        value_wei: tx.value_wei, block_number: tx.block_number, timestamp: tx.timestamp,
        risk_score: tx.risk_score, risk_factors: riskFactors(tx), relationship_context: tx.relationship_context || null,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `chainscope-evidence-${tx.hash.slice(0, 12)}.json`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
      onMessage('Evidence exported and recorded in the audit log.');
    } catch (error) { onMessage(error?.message || 'Unable to export evidence.', true); }
    finally { setBusy(false); }
  }

  return <div className="grid min-w-[168px] gap-1.5" aria-label={`Review actions for ${tx.hash}`}>
    <button disabled={busy} type="button" onClick={() => review('confirmed')} className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-1.5 text-left text-[11px] font-semibold text-emerald-100 disabled:opacity-50">✓ Confirm Risk</button>
    <button disabled={busy} type="button" onClick={() => review('false_positive')} className="rounded border border-slate-500/50 bg-slate-700/30 px-2 py-1.5 text-left text-[11px] font-semibold text-slate-100 disabled:opacity-50">× False Positive</button>
    <button disabled={busy} type="button" onClick={() => review('needs_review')} className="rounded border border-amber-500/35 bg-amber-500/10 px-2 py-1.5 text-left text-[11px] font-semibold text-amber-100 disabled:opacity-50">◷ Needs Review</button>
    <button disabled={busy} type="button" onClick={() => review('escalated')} className="rounded border border-violet-500/35 bg-violet-500/10 px-2 py-1.5 text-left text-[11px] font-semibold text-violet-100 disabled:opacity-50">↑ Escalate</button>
    <button disabled={busy} type="button" onClick={exportEvidence} className="rounded border border-sky-500/35 bg-sky-500/10 px-2 py-1.5 text-left text-[11px] font-semibold text-sky-100 disabled:opacity-50">⇩ Export evidence</button>
  </div>;
}

export default function TransactionList({
  transactions = [], onSelect, totalMatches = 0, matchingTransactions = 0, loading = false, error = null,
  onRetry, onClearFilters, onChanged, offset = 0, sort = 'risk_desc', onSort = () => {},
}) {
  const [actor, setActor] = useState(() => localStorage.getItem('chainscope_analyst') || 'Analyst');
  const [message, setMessage] = useState('');
  const [messageError, setMessageError] = useState(false);
  const shown = transactions.length;
  const total = Number(totalMatches || 0);
  const represented = Number(matchingTransactions || 0);
  const start = shown ? Number(offset) + 1 : 0;
  const end = shown ? Number(offset) + shown : 0;
  const partial = Boolean(error && shown);

  function updateActor(value) {
    setActor(value); localStorage.setItem('chainscope_analyst', value.trim() || 'Analyst');
  }

  function announce(text, isError = false) {
    setMessage(text); setMessageError(isError);
  }

  async function audit(tx, action, note) {
    try { await api.recordAnalystEvent(tx.hash, { action, actor: actor.trim() || 'Analyst', note }); } catch { /* evidence remains visible */ }
  }

  function handleRowKey(event, tx, index) {
    if (event.target?.closest('button, a, summary, input, details')) return;
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(tx); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const rows = Array.from(event.currentTarget.closest('tbody')?.querySelectorAll('tr[data-tx-row]') || []);
      const nextIndex = event.key === 'ArrowDown' ? Math.min(rows.length - 1, index + 1) : Math.max(0, index - 1);
      rows[nextIndex]?.focus();
    }
  }

  const rowContent = (tx, mobile = false) => {
    const score = Number(tx.risk_score) || 0;
    const risk = riskMeta(score);
    const amount = formatEth(tx);
    const clusterCount = Number(tx.cluster?.count || 1);
    const clusterWindow = durationLabel(tx.cluster?.oldest_timestamp, tx.cluster?.newest_timestamp);
    const actorName = actor.trim() || 'Analyst';
    const actions = <ReviewActions tx={tx} actor={actorName} onChanged={onChanged} onMessage={announce} />;

    if (mobile) return <article key={tx.hash} className="space-y-4 p-4">
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><span className="rounded border border-sky-400/30 bg-sky-400/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-sky-200">{clusterCount > 1 ? 'Cluster' : 'Transfer'}</span><p className="truncate font-mono text-sm text-slate-100">{shortHash(tx.hash)}</p></div><p className="mt-1 text-xs text-slate-400">{clusterCount > 1 ? `${clusterCount} transfers · ${clusterWindow}` : timeLabel(tx.timestamp)}</p></div><span className={`shrink-0 rounded border px-2 py-1 text-[11px] font-semibold ${risk.cls}`}>{risk.symbol} {risk.label} · {score || '—'}</span></div>
      <dl className="grid grid-cols-[58px_1fr] gap-x-2 gap-y-2 text-xs"><dt className="text-slate-400">From</dt><dd><AddressCell address={tx.from_address} matches={tx.entity_context?.sender} /></dd><dt className="text-slate-400">To</dt><dd><AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} /></dd><dt className="text-slate-400">Value</dt><dd className="text-white">{amount.text}</dd></dl>
      <FactorBreakdown tx={tx} onAudit={(action, note) => audit(tx, action, note)} />
      <ClusterSummary tx={tx} onSelect={onSelect} />
      <div className="grid grid-cols-2 gap-2">{actions}</div>
      <button type="button" onClick={() => { audit(tx, 'open_details', 'Opened full transaction detail.'); onSelect(tx); }} className="workspace-chip w-full">Full-screen detail</button>
    </article>;

    return <tr key={tx.hash} data-tx-row tabIndex="0" onKeyDown={event => handleRowKey(event, tx, transactions.indexOf(tx))} className="align-top hover:bg-white/[0.025] focus:bg-white/[0.04] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-sky-300">
      <td className="px-4 py-3"><div className="flex items-center gap-2"><span className="rounded border border-sky-400/30 bg-sky-400/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-sky-200">{clusterCount > 1 ? 'Cluster' : 'Transfer'}</span><span className="whitespace-nowrap text-xs text-slate-300">{clusterCount > 1 ? `${clusterCount} tx · ${clusterWindow}` : timeLabel(tx.timestamp)}</span></div><ClusterSummary tx={tx} onSelect={onSelect} /></td>
      <td className="px-4 py-3 font-mono text-xs text-slate-200" title={tx.hash}>{shortHash(tx.hash)}</td>
      <td className="px-4 py-3"><AddressCell address={tx.from_address} matches={tx.entity_context?.sender} /></td>
      <td className="px-4 py-3"><AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} /></td>
      <td className="whitespace-nowrap px-4 py-3 font-medium text-white" title={amount.title}>{amount.text}</td>
      <td className="px-4 py-3"><span className={`inline-flex rounded border px-2 py-1 text-xs font-semibold ${risk.cls}`}>{risk.symbol} {risk.label} · {score || '—'}</span></td>
      <td className="px-4 py-3"><FactorBreakdown tx={tx} onAudit={(action, note) => audit(tx, action, note)} /></td>
      <td className="px-4 py-3"><ReviewActions tx={tx} actor={actorName} onChanged={onChanged} onMessage={announce} /></td>
    </tr>;
  };

  return <section className="transaction-panel" aria-labelledby="transactions-heading" aria-busy={loading}>
    <div className="transaction-panel-head gap-4">
      <div><h2 id="transactions-heading" className="text-lg font-semibold text-white">Clustered Review Queue</h2><p className="mt-1 text-sm text-slate-300">Showing clusters {start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()}{represented ? ` · representing ${represented.toLocaleString()} matching transactions` : ''}</p></div>
      <label className="text-xs text-slate-300">Analyst identity <input aria-label="Analyst identity used in audit log" value={actor} onChange={event => updateActor(event.target.value)} className="ml-2 w-36 rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-300" /></label>
    </div>

    <div className="sr-only" aria-live="polite">{message}</div>
    {message && <div className={`mx-4 mt-4 rounded border px-3 py-2 text-xs ${messageError ? 'border-rose-400/30 bg-rose-400/10 text-rose-100' : 'border-sky-400/25 bg-sky-400/[0.07] text-sky-100'}`} role="status">{message}</div>}
    {partial && <div className="mx-4 mt-4 flex flex-wrap items-center justify-between gap-3 rounded border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100" role="status"><span>Live refresh failed. Showing the last successfully loaded clusters.</span><button type="button" onClick={onRetry} className="underline underline-offset-2">Retry live data</button></div>}

    {loading && !shown && <div className="space-y-3 p-6" role="status" aria-live="polite">{[0, 1, 2, 3, 4].map(i => <div key={i} className="h-16 animate-pulse rounded-lg bg-slate-800/70" />)}<span className="sr-only">Loading clustered review queue</span></div>}
    {!loading && error && !shown && <div className="py-14 text-center"><p className="font-semibold text-rose-100">Couldn’t reach the Ethereum data service.</p><p className="mt-2 text-sm text-slate-400">{error}</p><button type="button" onClick={onRetry} className="workspace-chip mt-4">Retry</button></div>}
    {!loading && !error && !shown && <div className="py-14 text-center"><p className="text-sm text-slate-300">No transactions match the active filters.</p>{onClearFilters && <button type="button" onClick={onClearFilters} className="workspace-chip mt-4">Clear filters</button>}</div>}

    {shown > 0 && <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm" role="table">
          <caption className="sr-only">Clustered Ethereum analyst review queue. Each row may represent multiple retained transfers.</caption>
          <thead className="border-y border-[#46566f] bg-[#111d31] text-xs uppercase tracking-wide text-slate-300"><tr>
            <SortHeader label="Cluster / Time" field="time" sort={sort === 'newest' ? 'time_desc' : sort === 'oldest' ? 'time_asc' : sort} onSort={value => onSort(value === 'time_desc' ? 'newest' : 'oldest')} />
            <th scope="col" className="px-4 py-3">Representative hash</th><th scope="col" className="px-4 py-3">From</th><th scope="col" className="px-4 py-3">To</th>
            <SortHeader label="Value" field="value" sort={sort} onSort={onSort} /><SortHeader label="Risk" field="risk" sort={sort} onSort={onSort} />
            <th scope="col" className="px-4 py-3">Why flagged</th><th scope="col" className="px-4 py-3">Action</th>
          </tr></thead>
          <tbody className="divide-y divide-[#46566f]">{transactions.map(tx => rowContent(tx))}</tbody>
        </table>
      </div>
      <div className="divide-y divide-[#46566f] md:hidden">{transactions.map(tx => rowContent(tx, true))}</div>
    </>}
  </section>;
}
