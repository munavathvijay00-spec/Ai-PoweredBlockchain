import { useEffect, useState } from 'react';
import { api } from '../api/client';

const ACTIONS = [
  ['needs_review', 'Needs review'],
  ['confirmed', 'Confirm signal'],
  ['false_positive', 'False positive'],
  ['escalated', 'Escalate'],
];

export default function AnalystReviewPanel({ txHash }) {
  const [status, setStatus] = useState('unreviewed');
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.getAnalystReview(txHash).then(data => {
      if (!active) return;
      setStatus(data.status || 'unreviewed');
      setAssignee(data.assignee || '');
      setNote(data.note || '');
    }).catch(() => {
      if (active) setMessage('Review state unavailable.');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [txHash]);

  async function save(nextStatus = status) {
    setSaving(true);
    setMessage('');
    try {
      const result = await api.saveAnalystReview(txHash, {
        status: nextStatus,
        assignee: assignee.trim() || null,
        note: note.trim() || null,
      });
      setStatus(result.status || nextStatus);
      setMessage('Review saved.');
    } catch (error) {
      setMessage(error?.message || 'Unable to save review.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-lg border border-sky-400/20 bg-sky-400/[0.04] p-4" aria-labelledby="analyst-actions-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id="analyst-actions-title" className="text-sm font-semibold uppercase tracking-wider text-sky-300">Analyst Actions</h3>
          <p className="mt-1 text-xs text-slate-500">Record the human decision separately from automated review signals.</p>
        </div>
        <span className="rounded-full border border-slate-600 bg-slate-800 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-300">{loading ? 'loading' : status.replaceAll('_', ' ')}</span>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {ACTIONS.map(([value, label]) => <button key={value} type="button" disabled={saving || loading} onClick={() => save(value)} className={`rounded-lg border px-3 py-2 text-xs font-semibold transition disabled:opacity-50 ${status === value ? 'border-sky-400/50 bg-sky-400/15 text-sky-100' : 'border-[#42516a] bg-[#111b2d] text-slate-300 hover:border-sky-400/30'}`}>{label}</button>)}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-[220px_1fr]">
        <label className="text-xs text-slate-400">Assignee
          <input value={assignee} onChange={event => setAssignee(event.target.value)} placeholder="Analyst name / team" className="mt-1 w-full rounded-lg border border-[#42516a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400" />
        </label>
        <label className="text-xs text-slate-400">Case note
          <textarea value={note} onChange={event => setNote(event.target.value)} rows="2" placeholder="Reason for decision, follow-up, evidence to verify…" className="mt-1 w-full resize-y rounded-lg border border-[#42516a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400" />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3"><button type="button" disabled={saving || loading} onClick={() => save(status)} className="workspace-chip disabled:opacity-50">{saving ? 'Saving…' : 'Save note / assignment'}</button>{message && <span className="text-xs text-slate-400" role="status">{message}</span>}</div>
    </section>
  );
}
