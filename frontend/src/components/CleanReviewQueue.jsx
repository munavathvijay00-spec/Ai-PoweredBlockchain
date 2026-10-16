import { useMemo, useState } from 'react';
import { api, hasAnalystCredential, setAnalystCredential } from '../api/client';

const short = (value, left = 8, right = 6) => value ? `${value.slice(0, left)}…${value.slice(-right)}` : '—';

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '').slice(0, 6);
    return `${whole}${fraction ? `.${fraction}` : ''} ETH`;
  }
  const value = Number(tx.value_eth);
  return Number.isFinite(value) ? `${value.toPrecision(6)} ETH` : '—';
}

function timeLabel(timestamp) {
  if (!timestamp) return 'Unknown time';
  const raw = String(timestamp);
  const date = new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? 'Unknown time' : `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

function riskMeta(score) {
  if (score >= 80) return ['Critical', 'border-red-500/40 bg-red-500/10 text-red-200'];
  if (score >= 40) return ['High review', 'border-orange-500/40 bg-orange-500/10 text-orange-200'];
  if (score >= 20) return ['Review', 'border-amber-500/40 bg-amber-500/10 text-amber-100'];
  if (score > 0) return ['Low signal', 'border-emerald-500/30 bg-emerald-500/[0.07] text-emerald-200'];
  return ['No signal', 'border-slate-600 bg-slate-800/50 text-slate-300'];
}

function factors(tx) {
  return (Array.isArray(tx.risk_factors) ? tx.risk_factors : []).filter(Boolean).map((item, index) => ({
    name: item.factor || item.name || item.type || `signal_${index + 1}`,
    reason: item.reason || item.name || item.type || 'Recorded review signal',
    points: Number(item.points || 0),
  }));
}

function ReviewDrawer({ tx, onClose, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [assignee, setAssignee] = useState('');
  const [message, setMessage] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [unlocked, setUnlocked] = useState(() => hasAnalystCredential());
  const hashes = useMemo(() => Array.isArray(tx?.cluster?.hashes) && tx.cluster.hashes.length ? tx.cluster.hashes : [tx?.hash], [tx]);
  if (!tx) return null;
  const score = Number(tx.risk_score || 0);
  const [riskLabel, riskClass] = riskMeta(score);
  const recordedFactors = factors(tx);

  function unlock() {
    const key = accessKey.trim();
    if (!key) { setMessage('Enter the analyst access key.'); return; }
    setAnalystCredential(key);
    setUnlocked(true);
    setAccessKey('');
    setMessage('Analyst mode unlocked for this browser tab.');
  }

  function lock() {
    setAnalystCredential('');
    setUnlocked(false);
    setMessage('Analyst mode locked.');
  }

  async function review(status) {
    if (!unlocked) { setMessage('Unlock analyst mode first.'); return; }
    if (!note.trim()) { setMessage('Add a short reason before saving a disposition.'); return; }
    if (status === 'escalated' && !assignee.trim()) { setMessage('Add an assignee before escalation.'); return; }
    setBusy(true); setMessage('');
    try {
      await api.saveClusterReview({ hashes, status, assignee: assignee.trim() || null, note: note.trim() });
      setMessage('Decision saved.');
      onChanged?.();
    } catch (error) {
      if (error?.status === 401 || error?.status === 403) {
        setAnalystCredential('');
        setUnlocked(false);
        setMessage('Access key was rejected. Enter the correct analyst key and unlock again.');
      } else setMessage(error?.message || 'Unable to save decision.');
    } finally { setBusy(false); }
  }

  async function exportEvidence() {
    const payload = {
      schema: 'chainscope-review-evidence/v2',
      exported_at: new Date().toISOString(),
      representative_hash: tx.hash,
      cluster_hashes: hashes,
      transaction: tx,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `chainscope-evidence-${tx.hash.slice(0, 12)}.json`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    if (unlocked) {
      try { await api.recordAnalystEvent(tx.hash, { action: 'export_evidence', note: `Exported evidence for ${hashes.length} retained transaction(s).` }); } catch {}
    }
  }

  return <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/55" role="dialog" aria-modal="true" aria-label="Review transaction cluster">
    <button aria-label="Close review panel" onClick={onClose} className="absolute inset-0 cursor-default" />
    <aside className="relative h-full w-full max-w-xl overflow-y-auto border-l border-slate-700 bg-[#111d31] p-5 shadow-2xl sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300">Focused review</p><h2 className="mt-2 text-xl font-semibold text-white">{short(tx.hash, 12, 10)}</h2><p className="mt-1 text-xs text-slate-400">{Number(tx.cluster?.count || 1)} retained transfer{Number(tx.cluster?.count || 1) === 1 ? '' : 's'} represented</p></div>
        <button onClick={onClose} className="workspace-chip">Close</button>
      </div>

      {!unlocked && <section className="mt-5 rounded-xl border border-sky-400/20 bg-sky-400/[0.05] p-4">
        <p className="text-sm font-semibold text-white">Unlock analyst mode</p>
        <p className="mt-1 text-xs text-slate-400">Enter the access key once. It is kept only for this browser tab.</p>
        <div className="mt-3 flex gap-2"><input type="password" value={accessKey} onChange={event => setAccessKey(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') unlock(); }} placeholder="Analyst access key" className="soft-input min-w-0 flex-1" /><button onClick={unlock} className="primary-button">Unlock</button></div>
      </section>}

      {unlocked && <div className="mt-5 flex items-center justify-between rounded-xl border border-emerald-400/20 bg-emerald-400/[0.05] px-4 py-3"><div><p className="text-sm font-medium text-emerald-200">Analyst mode unlocked</p><p className="mt-0.5 text-[11px] text-slate-500">No repeated authentication for this tab.</p></div><button onClick={lock} className="workspace-chip">Lock</button></div>}

      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-4"><p className="metric-label">Value</p><p className="mt-2 font-semibold text-white">{formatEth(tx)}</p></div>
        <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-4"><p className="metric-label">Risk</p><span className={`mt-2 inline-flex rounded border px-2 py-1 text-xs font-semibold ${riskClass}`}>{riskLabel} · {score}</span></div>
      </div>

      <section className="mt-5 rounded-xl border border-slate-700 bg-slate-950/35 p-4">
        <p className="metric-label">Observed route</p>
        <div className="mt-3 space-y-2 font-mono text-xs text-slate-300"><p><span className="text-slate-500">From </span>{tx.from_address}</p><p><span className="text-slate-500">To </span>{tx.to_address}</p></div>
      </section>

      <section className="mt-5 rounded-xl border border-slate-700 bg-slate-950/35 p-4">
        <div className="flex items-center justify-between gap-3"><p className="metric-label">Why flagged</p><span className="text-xs text-slate-500">Server-recorded signals</span></div>
        <div className="mt-3 space-y-2">{recordedFactors.length ? recordedFactors.map((factor, index) => <div key={`${factor.name}-${index}`} className="flex items-start justify-between gap-4 rounded-lg border border-slate-800 bg-slate-900/55 px-3 py-2 text-xs"><div><p className="font-medium text-slate-100">{factor.reason}</p><p className="mt-1 font-mono text-[10px] text-slate-500">{factor.name}</p></div><span className="font-semibold text-amber-200">+{factor.points}</span></div>) : <p className="text-sm text-slate-400">No recorded review factors.</p>}</div>
      </section>

      <section className={`mt-5 rounded-xl border p-4 ${unlocked ? 'border-slate-700 bg-slate-950/35' : 'border-slate-800 bg-slate-950/20 opacity-60'}`}>
        <p className="metric-label">Disposition</p>
        <textarea disabled={!unlocked} value={note} onChange={event => setNote(event.target.value)} placeholder="Short reason for the decision…" className="soft-input mt-3 min-h-20 w-full resize-y disabled:cursor-not-allowed" />
        <input disabled={!unlocked} value={assignee} onChange={event => setAssignee(event.target.value)} placeholder="Assignee / team (only for escalation)" className="soft-input mt-3 w-full disabled:cursor-not-allowed" />
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button disabled={busy || !unlocked} onClick={() => review('confirmed')} className="secondary-button disabled:opacity-40">Confirm risk</button>
          <button disabled={busy || !unlocked} onClick={() => review('false_positive')} className="secondary-button disabled:opacity-40">False positive</button>
          <button disabled={busy || !unlocked} onClick={() => review('needs_review')} className="secondary-button disabled:opacity-40">Needs review</button>
          <button disabled={busy || !unlocked} onClick={() => review('escalated')} className="secondary-button disabled:opacity-40">Escalate</button>
        </div>
        <button disabled={busy} onClick={exportEvidence} className="workspace-chip mt-3 w-full">Export evidence</button>
        {message && <p className="mt-3 text-xs text-sky-200" role="status">{message}</p>}
      </section>
    </aside>
  </div>;
}

export default function CleanReviewQueue({ transactions = [], onSelect, totalMatches = 0, loading = false, error = null, onRetry, onChanged, offset = 0, sort = 'risk_desc', onSort = () => {} }) {
  const [reviewTx, setReviewTx] = useState(null);
  const total = Number(totalMatches || 0);
  const start = transactions.length ? Number(offset) + 1 : 0;
  const end = transactions.length ? Number(offset) + transactions.length : 0;

  if (loading && !transactions.length) return <section className="transaction-panel p-6"><div className="space-y-3">{[0,1,2,3,4].map(i => <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800/70" />)}</div></section>;
  if (error && !transactions.length) return <section className="transaction-panel py-14 text-center"><p className="text-rose-200">Unable to load the review queue.</p><button onClick={onRetry} className="workspace-chip mt-4">Retry</button></section>;

  return <>
    <section className="transaction-panel" aria-label="Clustered review queue">
      <div className="transaction-panel-head"><div><h2 className="text-lg font-semibold text-white">Review Queue</h2><p className="mt-1 text-sm text-slate-400">{start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()} clusters · select only what needs attention</p></div></div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="border-y border-slate-700 bg-[#111d31] text-[11px] uppercase tracking-wide text-slate-400"><tr><th className="px-4 py-3">Time / Cluster</th><th className="px-4 py-3">Hash</th><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3"><button onClick={() => onSort(sort === 'value_desc' ? 'value_asc' : 'value_desc')}>Value ↕</button></th><th className="px-4 py-3"><button onClick={() => onSort(sort === 'risk_desc' ? 'risk_asc' : 'risk_desc')}>Risk ↕</button></th><th className="px-4 py-3 text-right">Review</th></tr></thead>
          <tbody className="divide-y divide-slate-700/80">{transactions.map(tx => {
            const score = Number(tx.risk_score || 0); const [label, cls] = riskMeta(score);
            return <tr key={tx.hash} onDoubleClick={() => onSelect?.(tx)} className="hover:bg-white/[0.025]"><td className="px-4 py-3"><p className="text-xs text-slate-300">{timeLabel(tx.timestamp)}</p><p className="mt-1 text-[10px] text-slate-500">{Number(tx.cluster?.count || 1)} transfer{Number(tx.cluster?.count || 1) === 1 ? '' : 's'}</p></td><td className="px-4 py-3 font-mono text-xs text-slate-200" title={tx.hash}>{short(tx.hash, 10, 8)}</td><td className="px-4 py-3 font-mono text-xs text-slate-300" title={tx.from_address}>{short(tx.from_address)}</td><td className="px-4 py-3 font-mono text-xs text-slate-300" title={tx.to_address}>{short(tx.to_address)}</td><td className="whitespace-nowrap px-4 py-3 font-medium text-white">{formatEth(tx)}</td><td className="px-4 py-3"><span className={`inline-flex rounded border px-2 py-1 text-xs font-semibold ${cls}`}>{label} · {score}</span></td><td className="px-4 py-3 text-right"><button onClick={() => setReviewTx(tx)} className="workspace-chip">Review</button></td></tr>;
          })}</tbody>
        </table>
      </div>
      <div className="divide-y divide-slate-700 md:hidden">{transactions.map(tx => { const score = Number(tx.risk_score || 0); const [label, cls] = riskMeta(score); return <article key={tx.hash} className="p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-mono text-sm text-white">{short(tx.hash, 10, 8)}</p><p className="mt-1 text-xs text-slate-500">{timeLabel(tx.timestamp)}</p></div><span className={`rounded border px-2 py-1 text-[11px] ${cls}`}>{label} · {score}</span></div><div className="mt-3 flex items-center justify-between"><p className="text-sm font-medium text-white">{formatEth(tx)}</p><button onClick={() => setReviewTx(tx)} className="workspace-chip">Review</button></div></article>; })}</div>
    </section>
    <ReviewDrawer tx={reviewTx} onClose={() => setReviewTx(null)} onChanged={onChanged} />
  </>;
}
