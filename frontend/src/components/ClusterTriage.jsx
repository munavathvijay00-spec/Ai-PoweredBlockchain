import { useMemo, useState } from 'react';

const short = value => value && value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : (value || 'Unknown');
const parseTime = value => {
  if (!value) return NaN;
  const raw = String(value);
  return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`);
};
const scoreLabel = value => value >= 80 ? 'Critical' : value >= 40 ? 'High review' : value >= 20 ? 'Review' : 'Low signal';

export default function ClusterTriage({ transactions = [], onSelect, loading = false }) {
  const [expanded, setExpanded] = useState({});
  const groups = useMemo(() => {
    const buckets = new Map();
    const unique = new Set();
    for (const tx of transactions) {
      if (!tx?.hash || unique.has(tx.hash.toLowerCase()) || !tx.from_address) continue;
      unique.add(tx.hash.toLowerCase());
      const timestamp = parseTime(tx.timestamp);
      if (!Number.isFinite(timestamp)) continue;
      const hour = Math.floor(timestamp / 3600000);
      const key = `${tx.from_address.toLowerCase()}:${hour}`;
      if (!buckets.has(key)) buckets.set(key, { key, address: tx.from_address, hour, items: [] });
      buckets.get(key).items.push(tx);
    }
    return [...buckets.values()]
      .filter(group => group.items.length >= 3)
      .map(group => ({ ...group, maxScore: Math.max(...group.items.map(tx => Number(tx.risk_score) || 0)) }))
      .sort((a, b) => b.maxScore - a.maxScore || b.items.length - a.items.length)
      .slice(0, 20);
  }, [transactions]);

  if (loading || !transactions.length) return null;
  return <section className="platform-card p-5" aria-labelledby="cluster-triage-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="cluster-triage-title" className="text-lg font-semibold text-white">Cluster triage</h2>
        <p className="mt-1 text-sm text-slate-400">Repeated sender activity grouped into UTC hour buckets, using only the currently loaded transaction page.</p></div>
      <span className="rounded-md border border-sky-400/20 bg-sky-400/[0.07] px-3 py-1 text-xs text-sky-300">{groups.length} page clusters</span>
    </div>
    <p className="mt-3 text-xs text-amber-200">Exploratory grouping, not a risk model. Counts may be incomplete across page boundaries and ingestion gaps. Cluster score is the highest recorded transaction score, not a newly calculated fraud score.</p>
    {groups.length === 0 ? <p className="mt-5 text-sm text-slate-400">No repeated sender groups of three or more records on this page.</p> :
      <div className="mt-4 space-y-3">{groups.map(group => {
        const open = !!expanded[group.key];
        const first = new Date(group.hour * 3600000).toISOString().slice(0, 16).replace('T', ' ');
        const end = new Date((group.hour + 1) * 3600000).toISOString().slice(0, 16).replace('T', ' ');
        return <div key={group.key} className="rounded-lg border border-slate-700 bg-slate-900/40">
          <button type="button" aria-expanded={open} onClick={() => setExpanded(previous => ({ ...previous, [group.key]: !open }))} className="flex w-full flex-wrap items-center justify-between gap-3 p-4 text-left hover:bg-white/[0.025]">
            <div><p className="font-mono text-sm font-semibold text-slate-100" title={group.address}>{short(group.address)}</p><p className="mt-1 text-xs text-slate-400">{group.items.length} observed page transactions · {first}–{end} UTC</p></div>
            <div className="flex items-center gap-3"><span className="text-xs font-medium text-amber-200">{scoreLabel(group.maxScore)} · {group.maxScore}</span><span className="text-sm text-sky-300">{open ? 'Collapse ▲' : 'Inspect ▼'}</span></div>
          </button>
          {open && <div className="border-t border-slate-700 p-4"><div className="space-y-2">{group.items.map(tx => {
            const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors.filter(f => f && typeof f === 'object') : [];
            return <div key={tx.hash} className="rounded-md bg-slate-800/60 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-xs text-slate-200" title={tx.hash}>{short(tx.hash)}</span><button type="button" onClick={() => onSelect(tx)} className="workspace-chip">View evidence</button></div>
              <p className="mt-2 text-xs text-slate-400">Recorded score: {Number(tx.risk_score) || 0} · {factors.length ? factors.map(f => `${f.factor || f.name || 'signal'} (+${Number(f.points) || 0})`).join(' · ') : 'No factor breakdown available'}</p>
            </div>;
          })}</div></div>}
        </div>;
      })}</div>}
  </section>;
}
