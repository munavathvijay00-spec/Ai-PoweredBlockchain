import { useEffect, useState } from 'react';
import { api } from '../api/client';

const ACTIONS = [
  ['needs_review', 'Needs review'],
  ['confirmed', 'Confirm risk'],
  ['false_positive', 'False positive'],
  ['escalated', 'Escalate'],
];

export default function AnalystReviewPanel({ txHash }) {
  const [status, setStatus] = useState('unreviewed');
  const [actor, setActor] = useState(() => localStorage.getItem('chainscope_analyst') || 'Analyst');
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([api.getAnalystReview(txHash), api.getAnalystAudit(txHash, 30)]).then(([review, history]) => {
      if (!active) return;
      setStatus(review.status || 'unreviewed');
      setAssignee(review.assignee || '');
      setNote(review.note || '');
      setAudit(history.events || []);
    }).catch(() => {
      if (active) setMessage('Review or audit state unavailable.');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [txHash]);

  function updateActor(value) {
    setActor(value);
    localStorage.setItem('chainscope_analyst', value.trim() || 'Analyst');
  }

  async function save(nextStatus = status) {
    const why = note.trim();
    if (!why) { setMessage('Add a case note explaining why before saving.'); return; }
    if (nextStatus === 'escalated' && !assignee.trim()) { setMessage('Escalation requires an assignee.'); return; }
    setSaving(true);
    setMessage('');
    try {
      const result = await api.saveAnalystReview(txHash, {
        status: nextStatus,
        actor: actor.trim() || 'Analyst',
        assignee: assignee.trim() || null,
        note: why,
      });
      setStatus(result.status || nextStatus);
      setMessage('Review saved and audit event recorded.');
      const history = await api.getAnalystAudit(txHash, 30);
      setAudit(history.events || []);
    } catch (error) {
      setMessage(error?.message || 'Unable to save review.');
    } finally {
      setSaving(false);
    }
  }

  return <section className="rounded-lg border border-sky-400/25 bg-sky-400/[0.05] p-4" aria-labelledby="analyst-actions-title">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 id="analyst-actions-title" className="text-sm font-semibold uppercase tracking-wider text-sky-200">Analyst Actions</h3><p className="mt-1 text-xs text-slate-400">Every decision is appended to the audit trail separately from automated signals.</p></div>
      <span className="rounded-full border border-slate-500 bg-slate-800 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-200">{loading ? 'loading' : status.replaceAll('_', ' ')}</span>
    </div>

    <div className="mt-4 grid gap-3 md:grid-cols-[220px_220px_1fr]">
      <label className="text-xs text-slate-300">Analyst identity<input value={actor} onChange={event => updateActor(event.target.value)} className="mt-1 w-full rounded-lg border border-[#56657a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-sky-300" /></label>
      <label className="text-xs text-slate-300">Assignee<input value={assignee} onChange={event => setAssignee(event.target.value)} placeholder="Analyst / team" className="mt-1 w-full rounded-lg border border-[#56657a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-sky-300" /></label>
      <label className="text-xs text-slate-300">Decision reason / case note<textarea value={note} onChange={event => setNote(event.target.value)} rows="2" placeholder="Required: evidence checked, reason for disposition, next step…" className="mt-1 w-full resize-y rounded-lg border border-[#56657a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-sky-300" /></label>
    </div>

    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{ACTIONS.map(([value, label]) => <button key={value} type="button" disabled={saving || loading} onClick={() => save(value)} className={`rounded-lg border px-3 py-2 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-sky-300 disabled:opacity-50 ${status === value ? 'border-sky-300/60 bg-sky-400/20 text-white' : 'border-[#56657a] bg-[#111b2d] text-slate-200 hover:border-sky-300/50'}`}>{label}</button>)}</div>
    {message && <p className="mt-3 text-xs text-slate-300" role="status" aria-live="polite">{message}</p>}

    <details className="mt-4 rounded-lg border border-slate-600/80 bg-slate-900/30 p-3">
      <summary className="cursor-pointer text-xs font-semibold text-slate-200">Audit trail ({audit.length})</summary>
      <div className="mt-3 max-h-56 space-y-2 overflow-auto">{audit.length ? audit.map(event => <div key={event.id} className="rounded border border-slate-700 bg-slate-950/40 p-2 text-[11px] text-slate-300"><div className="flex flex-wrap justify-between gap-2"><strong className="text-slate-100">{String(event.action || '').replaceAll('_', ' ')}</strong><span>{event.created_at ? new Date(event.created_at).toLocaleString() : 'time unavailable'}</span></div><p className="mt-1">Actor: {event.actor || 'unknown'} · {event.previous_status || '—'} → {event.new_status || '—'}{event.assignee ? ` · assigned ${event.assignee}` : ''}</p>{event.note && <p className="mt-1 text-slate-400">{event.note}</p>}</div>) : <p className="text-xs text-slate-500">No analyst events recorded yet.</p>}</div>
    </details>
  </section>;
}
