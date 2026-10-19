import { useState } from 'react';

const short = value => value && value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : (value || 'Unknown');
const tier = value => value >= 80 ? 'Critical' : value >= 40 ? 'High review' : value >= 20 ? 'Review' : 'Low signal';

export default function ClusterTriage({ transactions = [], onSelect, loading = false }) {
  const [expanded, setExpanded] = useState({});
  // Use the same server-side sender-recipient grouping as the transaction browser.
  // Never regroup a paginated subset into misleading hourly "clusters".
  const clusters = transactions.filter(tx => Number(tx?.cluster?.count || 0) > 1);
  return <section className="platform-card p-5" aria-labelledby="cluster-triage-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="cluster-triage-title" className="text-lg font-semibold text-white">Cluster triage</h2>
        <p className="mt-1 text-sm text-slate-400">Repeated sender → recipient pairs across the filtered retained population. These are observed links, not identity or fraud conclusions.</p></div>
      <span className="rounded-md border border-sky-400/20 bg-sky-400/[0.07] px-3 py-1 text-xs text-sky-300">{clusters.length} repeated clusters on this page</span>
    </div>
    {loading ? <p className="mt-4 text-sm text-slate-400" role="status">Loading clusters…</p> :
      clusters.length === 0 ? <p className="mt-4 text-sm text-slate-400">No repeated sender–recipient clusters on this page. Other filtered pages may contain repeated pairs.</p> :
      <div className="mt-4 grid gap-3 lg:grid-cols-2">{clusters.map(tx => {
        const key = `${tx.from_address}:${tx.to_address}`;
        const open = !!expanded[key];
        const count = Number(tx.cluster.count);
        const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors : [];
        return <article key={key} className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-xs text-slate-200" title={key}>{short(tx.from_address)} → {short(tx.to_address)}</p><span className="text-xs font-medium text-amber-200">{tier(Number(tx.risk_score) || 0)} · {Number(tx.risk_score) || 0}</span></div>
          <p className="mt-2 text-sm text-white">{count.toLocaleString()} matching retained transfers · {Number(tx.cluster.distinct_blocks || 0)} blocks</p>
          <p className="mt-1 text-xs text-slate-400">Representative transaction selected by highest recorded score; not a newly inferred cluster risk score.</p>
          <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => setExpanded(old => ({...old, [key]: !open}))} aria-expanded={open} className="workspace-chip">{open ? 'Hide evidence' : 'Why flagged?'}</button><button type="button" className="workspace-chip" onClick={() => onSelect(tx)}>Inspect transaction</button></div>
          {open && <div className="mt-3 border-t border-slate-700 pt-3 text-xs text-slate-300">
            {factors.length ? factors.map((factor, i) => <p key={i} className="mt-1">+{Number(factor.points) || 0} · {factor.reason || factor.factor || 'Recorded signal'}</p>) : <p>No recorded factors available.</p>}
            <p className="mt-2 text-slate-400">Recorded total: {Number(tx.risk_score) || 0}/100. Scores can be capped at 100; they are not fraud probabilities.</p>
            <p className="mt-2 text-slate-400">Transaction hashes retained in this group: {Array.isArray(tx.cluster.hashes) ? tx.cluster.hashes.length : 'Unknown'}. Review evidence before making a determination.</p>
          </div>}
        </article>;
      })}</div>}
  </section>;
}
