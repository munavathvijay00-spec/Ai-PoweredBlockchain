import { useState } from 'react';
import { bestAddressLabel } from '../utils/knownContracts';

const short = value => value && value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-6)}` : (value || 'Unknown');
const tier = score => score >= 80 ? 'Critical' : score >= 40 ? 'High review' : score >= 20 ? 'Review' : 'No recorded risk';
const when = value => {
  if (!value) return null;
  const date = new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(String(value)) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};
const duration = (start, end) => {
  const a = when(start), b = when(end);
  if (!a || !b) return 'Window unavailable';
  const minutes = Math.max(0, Math.round((b - a) / 60000));
  if (minutes < 60) return `${minutes} min observed`;
  const hours = minutes / 60;
  return hours < 48 ? `${hours.toFixed(1)} h observed` : `${(hours / 24).toFixed(1)} d observed`;
};
const amount = tx => {
  if (tx.value_wei == null || !/^\d+$/.test(String(tx.value_wei))) return 'Native value unavailable';
  const wei = BigInt(String(tx.value_wei));
  const whole = wei / 1000000000000000000n;
  const frac = (wei % 1000000000000000000n).toString().padStart(18, '0').slice(0, 5).replace(/0+$/, '');
  return `${whole}${frac ? '.' + frac : ''} ETH representative`;
};
function Identity({ address, matches }) {
  const label = bestAddressLabel(address, matches || []);
  return <span className="inline-flex min-w-0 flex-col">
    <span className="truncate font-mono text-slate-200" title={address}>{short(address)}</span>
    {label && <span className="truncate text-[11px] text-sky-300" title={label.label}>{label.label}</span>}
  </span>;
}

export default function ClusterTriage({ transactions = [], onSelect, loading = false }) {
  const [expanded, setExpanded] = useState({});
  const [includeLow, setIncludeLow] = useState(false);
  const [showAllHashes, setShowAllHashes] = useState({});
  // Server groups across the filtered retained population. We do NOT infer an
  // hourly cluster, a token transfer, or aggregate ETH from representative rows.
  const repeated = transactions.filter(tx => Number(tx?.cluster?.count || 0) > 1);
  const reviewable = repeated.filter(tx => Number(tx.risk_score || 0) >= 20);
  const low = repeated.filter(tx => Number(tx.risk_score || 0) < 20);
  const visible = includeLow ? [...reviewable, ...low] : reviewable;
  return <section className="platform-card p-5" aria-labelledby="cluster-triage-title">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="cluster-triage-title" className="text-lg font-semibold text-white">Cluster review queue</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">Repeated sender → recipient pairs across the filtered retained population. Prioritized by the highest recorded transaction score, not by inferred fraud or a cluster-wide score.</p>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-amber-200">{reviewable.length} review-priority on this page</span>
        <span className="rounded-md border border-slate-600 px-3 py-2 text-slate-300">{low.length} low-signal on this page</span>
      </div>
    </header>
    {low.length > 0 && <div className="mt-4">
      <button type="button" className="workspace-chip" aria-pressed={includeLow} onClick={() => setIncludeLow(value => !value)}>{includeLow ? 'Hide low-signal groups' : `Show ${low.length} low-signal groups`}</button>
    </div>}
    {loading ? <p className="mt-5 text-sm text-slate-400" role="status">Loading retained-population clusters…</p>
    : visible.length === 0 ? <p className="mt-5 rounded-lg border border-slate-700 bg-slate-900/40 p-4 text-sm text-slate-400" role="status">{repeated.length ? 'No review-priority clusters on this page. Low-signal repeats are available above.' : 'No repeated sender–recipient pairs on this page. Other pages may contain them.'}</p>
    : <div className="mt-4 space-y-2">{visible.map(tx => {
      const key = `${tx.from_address?.toLowerCase() || ''}:${tx.to_address?.toLowerCase() || ''}`;
      const score = Number(tx.risk_score || 0);
      const count = Number(tx.cluster.count);
      const hashes = Array.isArray(tx.cluster.hashes) ? tx.cluster.hashes : [];
      const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors : [];
      const open = !!expanded[key];
      const shown = showAllHashes[key] ? hashes.slice(0, 100) : hashes.slice(0, 10);
      const factorTotal = factors.reduce((sum, factor) => sum + (Number(factor?.points) || 0), 0);
      const positive = factors.filter(factor => Number(factor?.points || 0) > 0);
      return <article key={key} className="rounded-lg border border-slate-700 bg-slate-900/40">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 p-3 sm:p-4">
          <div className="min-w-0 flex-[2_1_230px]">
            <div className="flex min-w-0 items-center gap-2 text-xs"><Identity address={tx.from_address} matches={tx.entity_context?.sender}/><span aria-hidden="true" className="text-slate-500">→</span><Identity address={tx.to_address} matches={tx.entity_context?.recipient}/></div>
          </div>
          <div className="flex flex-[2_1_240px] flex-wrap gap-x-5 gap-y-2 text-xs">
            <div><span className="block text-slate-500">Observed transfers</span><span className="font-semibold text-slate-100">{count.toLocaleString()} · {Number(tx.cluster.distinct_blocks || 0)} blocks</span></div>
            <div><span className="block text-slate-500">Observation span</span><span className="font-medium text-slate-200">{duration(tx.cluster.oldest_timestamp, tx.cluster.newest_timestamp)}</span></div>
            <div><span className="block text-slate-500">Native value</span><span className="font-medium text-slate-200">{amount(tx)}</span></div>
          </div>
          <div className="flex flex-[1_1_190px] items-center justify-between gap-2">
            <span className={`text-xs font-semibold ${score >= 80 ? 'text-red-300' : score >= 40 ? 'text-orange-300' : score >= 20 ? 'text-amber-200' : 'text-slate-400'}`}>{tier(score)} · {score}</span>
            <button type="button" className="workspace-chip" onClick={() => setExpanded(old => ({...old, [key]: !open}))} aria-expanded={open} aria-label={`${open ? 'Hide' : 'View'} evidence for ${tx.from_address} to ${tx.to_address}`}>{open ? 'Close' : 'View evidence'}</button>
          </div>
        </div>
        {open && <div className="border-t border-slate-700 p-4 text-xs text-slate-300">
          <p className="font-medium text-slate-100">Recorded factors for the representative transaction</p>
          {positive.length ? <ul className="mt-2 space-y-1">{positive.map((factor, index) => <li key={index} className="flex justify-between gap-3"><span>{factor.reason || factor.factor || 'Recorded signal'}</span><span className="shrink-0 font-semibold text-amber-200">+{Number(factor.points)}</span></li>)}</ul> : <p className="mt-2 text-slate-400">No positive risk factors recorded. Repetition alone does not prove suspicious activity.</p>}
          <p className="mt-2 text-slate-400">Representative score {score}/100 · factor sum {factorTotal} (capped at 100). No group-wide risk score is inferred.</p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="font-medium text-slate-200">Transaction evidence · {hashes.length} loaded of {count} matching</p>
            <button className="workspace-chip" type="button" onClick={() => onSelect(tx)}>Inspect representative transaction</button>
          </div>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2" aria-label="Cluster transaction evidence">{shown.map(hash => <li key={hash} className="flex min-w-0 items-center justify-between gap-2 rounded-md bg-slate-800/50 p-2"><span className="truncate font-mono" title={hash}>{short(hash)}</span><a href={`https://etherscan.io/tx/${encodeURIComponent(hash)}`} target="_blank" rel="noopener noreferrer" className="shrink-0 text-sky-300 hover:underline" aria-label={`View transaction ${hash} on Etherscan`}>Explorer ↗</a></li>)}</ul>
          {hashes.length > 10 && <button type="button" className="mt-3 text-sky-300 hover:underline" onClick={() => setShowAllHashes(old => ({...old, [key]: !old[key]}))}>{showAllHashes[key] ? 'Show fewer hashes' : `Show more hashes (up to ${hashes.length})`}</button>}
          {count > hashes.length && <p className="mt-2 text-slate-500">Evidence links are limited to the first {hashes.length} retained hashes; the group count covers the full filtered retained population.</p>}
          <p className="mt-2 text-slate-500">Native ETH value describes the representative transaction only. Token totals and historical baselines are not available in this cluster response.</p>
        </div>}
      </article>;
    })}</div>}
  </section>;
}
