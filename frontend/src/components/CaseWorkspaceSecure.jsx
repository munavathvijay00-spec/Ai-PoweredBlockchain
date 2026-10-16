import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';

function downloadJson(name, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function CaseWorkspaceSecure({ initialEvidence = null, onEvidenceConsumed }) {
  const [session, setSession] = useState('checking');
  const [accessKey, setAccessKey] = useState('');
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [selected, setSelected] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', assignee: '' });
  const [item, setItem] = useState({ item_type: 'transaction', item_key: '', note: '' });
  const [stateForm, setStateForm] = useState({ status: 'in_progress', priority: 'medium', assignee: '', note: '' });

  useEffect(() => {
    let active = true;
    api.getAnalystSession().then(() => {
      if (active) setSession('active');
    }).catch(() => {
      if (active) setSession('locked');
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!initialEvidence) return;
    setItem({
      item_type: initialEvidence.item_type || 'address',
      item_key: initialEvidence.item_key || '',
      note: initialEvidence.note || '',
    });
    onEvidenceConsumed?.();
  }, [initialEvidence, onEvidenceConsumed]);

  async function signIn(event) {
    event.preventDefault();
    if (!accessKey.trim()) return;
    setAuthLoading(true); setError('');
    try {
      await api.createAnalystSession(accessKey.trim());
      setAccessKey('');
      setSession('active');
    } catch (failure) {
      setError(failure.status === 401 || failure.status === 403
        ? 'Access key rejected. Use the deployment API_KEY, ANALYST_API_KEY, or ADMIN_API_KEY.'
        : (failure.message || 'Unable to start analyst session.'));
    } finally {
      setAuthLoading(false);
    }
  }

  async function signOut() {
    setError('');
    try { await api.clearAnalystSession(); } catch { /* cookie expiry still limits session */ }
    setSession('locked');
    setCases([]); setSelected(null); setSelectedId('');
  }

  async function loadCases(filter = statusFilter) {
    if (session !== 'active') return;
    setLoading(true); setError('');
    try {
      const data = await api.listCases(filter);
      const rows = data.cases || [];
      setCases(rows);
      if (!selectedId && rows[0]?.id) setSelectedId(rows[0].id);
    } catch (failure) {
      if (failure.status === 401 || failure.status === 403) setSession('locked');
      setError(failure.message || 'Unable to load cases.');
    } finally { setLoading(false); }
  }

  useEffect(() => { loadCases(); }, [statusFilter, session]);

  useEffect(() => {
    let active = true;
    if (!selectedId || session !== 'active') { setSelected(null); return; }
    api.getCase(selectedId).then(data => {
      if (!active) return;
      setSelected(data);
      setStateForm({
        status: data.status || 'in_progress',
        priority: data.priority || 'medium',
        assignee: data.assignee || '',
        note: '',
      });
    }).catch(failure => {
      if (active) setError(failure.message || 'Unable to load case.');
    });
    return () => { active = false; };
  }, [selectedId, session]);

  async function createCase(event) {
    event.preventDefault(); setError('');
    try {
      const created = await api.createCase({ ...form, assignee: form.assignee || null });
      setForm({ title: '', description: '', priority: 'medium', assignee: '' });
      await loadCases();
      setSelectedId(created.id);
    } catch (failure) { setError(failure.message || 'Unable to create case.'); }
  }

  async function addItem(event) {
    event.preventDefault(); if (!selectedId) return;
    try {
      await api.addCaseItem(selectedId, { ...item, note: item.note || null });
      setItem({ item_type: 'transaction', item_key: '', note: '' });
      const data = await api.getCase(selectedId); setSelected(data); await loadCases();
    } catch (failure) { setError(failure.message || 'Unable to add evidence.'); }
  }

  async function updateCase(event) {
    event.preventDefault(); if (!selectedId || !stateForm.note.trim()) return;
    try {
      await api.updateCase(selectedId, { ...stateForm, assignee: stateForm.assignee || null });
      const data = await api.getCase(selectedId); setSelected(data);
      setStateForm(value => ({ ...value, note: '' }));
      await loadCases();
    } catch (failure) { setError(failure.message || 'Unable to update case.'); }
  }

  async function exportJson(kind) {
    if (!selectedId) return;
    try {
      const data = kind === 'bundle' ? await api.getCaseBundle(selectedId) : await api.getCaseReport(selectedId);
      downloadJson(`chainscope-${kind}-${selectedId}.json`, data);
    } catch (failure) { setError(failure.message || `Unable to export ${kind}.`); }
  }

  const counts = useMemo(() => ({
    open: cases.filter(row => row.status === 'open').length,
    active: cases.filter(row => row.status === 'in_progress').length,
    escalated: cases.filter(row => row.status === 'escalated').length,
  }), [cases]);

  if (session === 'checking') return <section className="panel p-6"><p className="text-sm text-slate-300">Checking analyst session…</p></section>;

  if (session !== 'active') return <div className="space-y-5">
    <section className="panel-strong p-5 sm:p-6">
      <p className="eyebrow">Restricted analyst workspace</p>
      <h2 className="mt-2 text-xl font-semibold text-white">Sign in to case management</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Enter a privileged deployment credential once. ChainScope verifies it server-side, discards the raw value, and returns only a short-lived HttpOnly analyst session cookie. The credential is not stored in localStorage or sessionStorage.</p>
      {initialEvidence && <div className="mt-4 rounded-lg border border-sky-400/20 bg-sky-400/[0.05] p-3 text-sm text-sky-100">Wallet evidence from Investigation Lab is ready and will remain queued after sign-in.</div>}
      <form onSubmit={signIn} className="mt-5 flex max-w-2xl flex-col gap-3 sm:flex-row">
        <input type="password" value={accessKey} onChange={e => setAccessKey(e.target.value)} className="soft-input min-w-0 flex-1" placeholder="Deployment access key" aria-label="Deployment access key" autoComplete="current-password" />
        <button className="primary-button" disabled={!accessKey.trim() || authLoading}>{authLoading ? 'Signing in…' : 'Start analyst session'}</button>
      </form>
      <p className="mt-3 text-xs leading-5 text-slate-400">Your current Railway deployment already has <code>API_KEY</code>, so that key can bootstrap the analyst session. For teams, add a dedicated <code>ANALYST_API_KEY</code> later and rotate the bootstrap key.</p>
      {error && <div role="alert" className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-100">{error}</div>}
    </section>
  </div>;

  return <div className="space-y-5">
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Case summary">
      <div className="panel p-4"><p className="eyebrow">Cases loaded</p><p className="mt-3 text-2xl font-semibold text-white">{cases.length}</p></div>
      <div className="panel p-4"><p className="eyebrow">Open</p><p className="mt-3 text-2xl font-semibold text-sky-300">{counts.open}</p></div>
      <div className="panel p-4"><p className="eyebrow">In progress</p><p className="mt-3 text-2xl font-semibold text-amber-200">{counts.active}</p></div>
      <div className="panel p-4"><p className="eyebrow">Escalated</p><p className="mt-3 text-2xl font-semibold text-rose-300">{counts.escalated}</p></div>
    </section>

    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="soft-input" aria-label="Filter cases by status">
        <option value="">All statuses</option><option value="open">Open</option><option value="in_progress">In progress</option><option value="escalated">Escalated</option><option value="closed">Closed</option>
      </select>
      <button onClick={signOut} className="secondary-button">End analyst session</button>
    </div>
    {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-100">{error}</div>}

    <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-5">
        <form onSubmit={createCase} className="panel space-y-3 p-5">
          <div><p className="eyebrow">New investigation</p><h3 className="mt-2 font-semibold text-white">Create case</h3></div>
          <input value={form.title} onChange={e => setForm(v => ({ ...v, title: e.target.value }))} className="soft-input w-full" placeholder="Case title" minLength={3} required />
          <textarea value={form.description} onChange={e => setForm(v => ({ ...v, description: e.target.value }))} className="soft-input min-h-24 w-full" placeholder="Investigation objective and scope" />
          <div className="grid gap-2 sm:grid-cols-2"><select value={form.priority} onChange={e => setForm(v => ({ ...v, priority: e.target.value }))} className="soft-input"><option>low</option><option>medium</option><option>high</option><option>critical</option></select><input value={form.assignee} onChange={e => setForm(v => ({ ...v, assignee: e.target.value }))} className="soft-input" placeholder="Assignee" /></div>
          <button className="primary-button w-full">Create case</button>
        </form>

        <section className="panel overflow-hidden p-0">
          <div className="border-b border-slate-700 px-4 py-3"><p className="eyebrow">Case queue</p></div>
          <div className="max-h-[520px] overflow-y-auto">
            {loading && <p className="p-4 text-sm text-slate-300">Loading cases…</p>}
            {!loading && !cases.length && <p className="p-4 text-sm text-slate-300">No cases match this filter.</p>}
            {cases.map(caseItem => <button key={caseItem.id} onClick={() => setSelectedId(caseItem.id)} className={`block min-h-16 w-full border-b border-slate-700/70 px-4 py-4 text-left hover:bg-slate-800/35 ${selectedId === caseItem.id ? 'bg-sky-400/[0.06]' : ''}`}><div className="flex items-start justify-between gap-2"><p className="font-medium text-white">{caseItem.title}</p><span className="text-xs uppercase text-slate-300">{caseItem.priority}</span></div><p className="mt-2 text-sm text-slate-300">{caseItem.status.replace('_', ' ')} · {caseItem.evidence_items || 0} evidence items</p><p className="mt-1 font-mono text-xs text-slate-400">{short(caseItem.id)}</p></button>)}
          </div>
        </section>
      </div>

      <div className="space-y-5">
        {!selected && <section className="panel p-8 text-sm text-slate-300">Select a case to open its evidence and audit timeline.</section>}
        {selected && <>
          <section className="panel-strong p-5 sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><p className="eyebrow">Investigation case</p><h2 className="mt-2 text-xl font-semibold text-white">{selected.title}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{selected.description || 'No description provided.'}</p></div><div className="flex flex-col gap-2 sm:flex-row"><button onClick={() => exportJson('report')} className="secondary-button">Export report</button><button onClick={() => exportJson('bundle')} className="primary-button">Export evidence bundle</button></div></div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><div><p className="eyebrow">Status</p><p className="mt-1 text-sm text-white">{selected.status}</p></div><div><p className="eyebrow">Priority</p><p className="mt-1 text-sm text-white">{selected.priority}</p></div><div><p className="eyebrow">Assignee</p><p className="mt-1 text-sm text-white">{selected.assignee || 'Unassigned'}</p></div><div><p className="eyebrow">Created by</p><p className="mt-1 text-sm text-white">{selected.created_by}</p></div></div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <form onSubmit={addItem} className="panel space-y-3 p-5"><p className="eyebrow">Add evidence</p>{item.item_key && <div className="rounded-lg border border-cyan-400/20 bg-cyan-400/[0.05] p-3 text-sm text-cyan-100">Evidence ready from Investigation Lab.</div>}<div className="grid gap-2 sm:grid-cols-[130px_1fr]"><select value={item.item_type} onChange={e => setItem(v => ({ ...v, item_type: e.target.value }))} className="soft-input"><option>transaction</option><option>address</option><option>entity</option></select><input value={item.item_key} onChange={e => setItem(v => ({ ...v, item_key: e.target.value }))} className="soft-input min-w-0 font-mono" placeholder="Evidence identifier" required /></div><textarea value={item.note} onChange={e => setItem(v => ({ ...v, note: e.target.value }))} className="soft-input min-h-20 w-full" placeholder="Evidence note" /><button className="primary-button">Add to case</button></form>
            <form onSubmit={updateCase} className="panel space-y-3 p-5"><p className="eyebrow">Case state</p><div className="grid gap-2 sm:grid-cols-2"><select value={stateForm.status} onChange={e => setStateForm(v => ({ ...v, status: e.target.value }))} className="soft-input"><option value="open">open</option><option value="in_progress">in progress</option><option value="escalated">escalated</option><option value="closed">closed</option></select><select value={stateForm.priority} onChange={e => setStateForm(v => ({ ...v, priority: e.target.value }))} className="soft-input"><option>low</option><option>medium</option><option>high</option><option>critical</option></select></div><input value={stateForm.assignee} onChange={e => setStateForm(v => ({ ...v, assignee: e.target.value }))} className="soft-input w-full" placeholder="Assignee" /><textarea value={stateForm.note} onChange={e => setStateForm(v => ({ ...v, note: e.target.value }))} className="soft-input min-h-20 w-full" placeholder="Required audit note" required /><button className="primary-button">Update case</button></form>
          </div>

          <section className="panel p-5"><div className="flex items-center justify-between"><p className="eyebrow">Evidence register</p><span className="text-sm text-slate-300">{selected.items?.length || 0} items</span></div><div className="mt-4 space-y-2">{(selected.items || []).map(row => <div key={row.id} className="rounded-lg border border-slate-700 bg-slate-950/35 p-3"><div className="flex flex-wrap items-center gap-2"><span className="rounded border border-slate-600 px-2 py-0.5 text-xs uppercase text-slate-300">{row.item_type}</span><span className="break-all font-mono text-sm text-cyan-300">{row.item_key}</span></div>{row.note && <p className="mt-2 text-sm text-slate-300">{row.note}</p>}</div>)}{!selected.items?.length && <p className="text-sm text-slate-300">No evidence has been added yet.</p>}</div></section>

          <section className="panel p-5"><div className="flex items-center justify-between"><p className="eyebrow">Audit timeline</p><span className="text-sm text-slate-300">{selected.audit?.length || 0} events</span></div><div className="mt-4 space-y-3">{(selected.audit || []).map(row => <div key={row.id} className="border-l-2 border-sky-400/30 pl-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium text-white">{String(row.action || '').replaceAll('_', ' ')}</p><span className="text-xs text-slate-400">{row.created_at ? new Date(row.created_at).toLocaleString() : 'time unavailable'}</span></div><p className="mt-1 text-sm text-slate-300">Actor: {row.actor || 'unknown'}</p>{row.note && <p className="mt-1 text-sm text-slate-400">{row.note}</p>}</div>)}</div></section>
        </>}
      </div>
    </div>
  </div>;
}
