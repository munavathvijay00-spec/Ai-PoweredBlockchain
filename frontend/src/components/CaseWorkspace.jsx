import { useEffect, useMemo, useState } from 'react';
import { api, hasAnalystCredential, setAnalystCredential } from '../api/client';

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

export default function CaseWorkspace() {
  const [credential, setCredential] = useState('');
  const [unlocked, setUnlocked] = useState(hasAnalystCredential());
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', assignee: '' });
  const [item, setItem] = useState({ item_type: 'transaction', item_key: '', note: '' });
  const [stateForm, setStateForm] = useState({ status: 'in_progress', priority: 'medium', assignee: '', note: '' });

  async function loadCases(filter = statusFilter) {
    if (!hasAnalystCredential()) return;
    setLoading(true); setError('');
    try {
      const data = await api.listCases(filter);
      setCases(data.cases || []);
      if (!selectedId && data.cases?.[0]?.id) setSelectedId(data.cases[0].id);
    } catch (failure) {
      setError(failure.status === 401 ? 'Unlock analyst access to load cases.' : (failure.message || 'Unable to load cases.'));
    } finally { setLoading(false); }
  }

  useEffect(() => { loadCases(); }, [statusFilter, unlocked]);

  useEffect(() => {
    let active = true;
    if (!selectedId || !hasAnalystCredential()) { setSelected(null); return; }
    api.getCase(selectedId).then(data => {
      if (!active) return;
      setSelected(data);
      setStateForm({ status: data.status || 'in_progress', priority: data.priority || 'medium', assignee: data.assignee || '', note: '' });
    }).catch(failure => active && setError(failure.message || 'Unable to load case.'));
    return () => { active = false; };
  }, [selectedId]);

  function unlock(event) {
    event.preventDefault();
    setAnalystCredential(credential);
    setCredential('');
    setUnlocked(hasAnalystCredential());
  }

  function lock() {
    setAnalystCredential(''); setUnlocked(false); setCases([]); setSelected(null); setSelectedId('');
  }

  async function createCase(event) {
    event.preventDefault(); setError('');
    try {
      const created = await api.createCase({ ...form, assignee: form.assignee || null });
      setForm({ title: '', description: '', priority: 'medium', assignee: '' });
      await loadCases(); setSelectedId(created.id);
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
      const data = await api.getCase(selectedId); setSelected(data); setStateForm(value => ({ ...value, note: '' })); await loadCases();
    } catch (failure) { setError(failure.message || 'Unable to update case.'); }
  }

  async function exportReport() {
    if (!selectedId) return;
    try {
      const report = await api.getCaseReport(selectedId);
      downloadJson(`chainscope-case-${selectedId}.json`, report);
    } catch (failure) { setError(failure.message || 'Unable to export case report.'); }
  }

  const counts = useMemo(() => ({
    open: cases.filter(item => item.status === 'open').length,
    active: cases.filter(item => item.status === 'in_progress').length,
    escalated: cases.filter(item => item.status === 'escalated').length,
  }), [cases]);

  if (!unlocked) return <div className="space-y-5">
    <section className="panel-strong p-6">
      <p className="eyebrow">Restricted analyst workspace</p>
      <h2 className="mt-2 text-xl font-semibold text-white">Unlock case management</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">Case data is protected by the server-side viewer/analyst role. Credentials are stored in this browser session only.</p>
      <form onSubmit={unlock} className="mt-5 flex max-w-2xl flex-col gap-3 sm:flex-row">
        <input type="password" value={credential} onChange={e => setCredential(e.target.value)} className="soft-input flex-1" placeholder="Viewer or analyst access key" aria-label="Analyst access key" />
        <button className="primary-button" disabled={!credential.trim()}>Unlock</button>
      </form>
    </section>
  </div>;

  return <div className="space-y-5">
    <section className="grid gap-3 sm:grid-cols-4">
      <div className="panel p-4"><p className="eyebrow">Cases loaded</p><p className="mt-3 text-2xl font-semibold text-white">{cases.length}</p></div>
      <div className="panel p-4"><p className="eyebrow">Open</p><p className="mt-3 text-2xl font-semibold text-sky-300">{counts.open}</p></div>
      <div className="panel p-4"><p className="eyebrow">In progress</p><p className="mt-3 text-2xl font-semibold text-amber-300">{counts.active}</p></div>
      <div className="panel p-4"><p className="eyebrow">Escalated</p><p className="mt-3 text-2xl font-semibold text-rose-300">{counts.escalated}</p></div>
    </section>

    <div className="flex flex-wrap items-center justify-between gap-3">
      <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="soft-input" aria-label="Filter cases by status">
        <option value="">All statuses</option><option value="open">Open</option><option value="in_progress">In progress</option><option value="escalated">Escalated</option><option value="closed">Closed</option>
      </select>
      <button onClick={lock} className="secondary-button">Lock analyst access</button>
    </div>
    {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-200">{error}</div>}

    <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-5">
        <form onSubmit={createCase} className="panel p-5 space-y-3">
          <div><p className="eyebrow">New investigation</p><h3 className="mt-2 font-semibold text-white">Create case</h3></div>
          <input value={form.title} onChange={e => setForm(v => ({ ...v, title: e.target.value }))} className="soft-input w-full" placeholder="Case title" minLength={3} required />
          <textarea value={form.description} onChange={e => setForm(v => ({ ...v, description: e.target.value }))} className="soft-input min-h-24 w-full" placeholder="Investigation objective and scope" />
          <div className="grid grid-cols-2 gap-2"><select value={form.priority} onChange={e => setForm(v => ({ ...v, priority: e.target.value }))} className="soft-input"><option>low</option><option>medium</option><option>high</option><option>critical</option></select><input value={form.assignee} onChange={e => setForm(v => ({ ...v, assignee: e.target.value }))} className="soft-input" placeholder="Assignee" /></div>
          <button className="primary-button w-full">Create case</button>
        </form>

        <section className="panel overflow-hidden">
          <div className="border-b border-slate-800 px-4 py-3"><p className="eyebrow">Case queue</p></div>
          <div className="max-h-[520px] overflow-y-auto">
            {loading && <p className="p-4 text-sm text-slate-500">Loading cases…</p>}
            {!loading && !cases.length && <p className="p-4 text-sm text-slate-500">No cases match this filter.</p>}
            {cases.map(item => <button key={item.id} onClick={() => setSelectedId(item.id)} className={`block w-full border-b border-slate-800/70 px-4 py-4 text-left hover:bg-slate-800/35 ${selectedId === item.id ? 'bg-sky-400/[0.06]' : ''}`}>
              <div className="flex items-start justify-between gap-2"><p className="font-medium text-white">{item.title}</p><span className="text-[10px] uppercase text-slate-500">{item.priority}</span></div>
              <p className="mt-2 text-xs text-slate-400">{item.status.replace('_', ' ')} · {item.evidence_items || 0} evidence items</p>
              <p className="mt-1 font-mono text-[10px] text-slate-600">{short(item.id)}</p>
            </button>)}
          </div>
        </section>
      </div>

      <div className="space-y-5">
        {!selected && <section className="panel p-8 text-sm text-slate-400">Select a case to open its evidence and audit timeline.</section>}
        {selected && <>
          <section className="panel-strong p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Investigation case</p><h2 className="mt-2 text-xl font-semibold text-white">{selected.title}</h2><p className="mt-2 max-w-3xl text-sm text-slate-400">{selected.description || 'No description provided.'}</p></div><button onClick={exportReport} className="secondary-button">Export evidence report</button></div>
            <div className="mt-5 grid gap-3 sm:grid-cols-4"><div><p className="eyebrow">Status</p><p className="mt-1 text-sm text-white">{selected.status}</p></div><div><p className="eyebrow">Priority</p><p className="mt-1 text-sm text-white">{selected.priority}</p></div><div><p className="eyebrow">Assignee</p><p className="mt-1 text-sm text-white">{selected.assignee || 'Unassigned'}</p></div><div><p className="eyebrow">Created by</p><p className="mt-1 text-sm text-white">{selected.created_by}</p></div></div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <form onSubmit={addItem} className="panel p-5 space-y-3"><p className="eyebrow">Add evidence</p><div className="grid grid-cols-[130px_1fr] gap-2"><select value={item.item_type} onChange={e => setItem(v => ({ ...v, item_type: e.target.value }))} className="soft-input"><option>transaction</option><option>address</option><option>entity</option></select><input value={item.item_key} onChange={e => setItem(v => ({ ...v, item_key: e.target.value }))} className="soft-input font-mono" placeholder="Evidence identifier" required /></div><textarea value={item.note} onChange={e => setItem(v => ({ ...v, note: e.target.value }))} className="soft-input min-h-20 w-full" placeholder="Evidence note" /><button className="primary-button">Add to case</button></form>
            <form onSubmit={updateCase} className="panel p-5 space-y-3"><p className="eyebrow">Case state</p><div className="grid grid-cols-2 gap-2"><select value={stateForm.status} onChange={e => setStateForm(v => ({ ...v, status: e.target.value }))} className="soft-input"><option value="open">open</option><option value="in_progress">in progress</option><option value="escalated">escalated</option><option value="closed">closed</option></select><select value={stateForm.priority} onChange={e => setStateForm(v => ({ ...v, priority: e.target.value }))} className="soft-input"><option>low</option><option>medium</option><option>high</option><option>critical</option></select></div><input value={stateForm.assignee} onChange={e => setStateForm(v => ({ ...v, assignee: e.target.value }))} className="soft-input w-full" placeholder="Assignee" /><textarea value={stateForm.note} onChange={e => setStateForm(v => ({ ...v, note: e.target.value }))} className="soft-input min-h-20 w-full" placeholder="Required audit note" required /><button className="primary-button">Update case</button></form>
          </div>

          <section className="panel p-5"><div className="flex items-center justify-between"><p className="eyebrow">Evidence register</p><span className="text-xs text-slate-500">{selected.items?.length || 0} items</span></div><div className="mt-4 space-y-2">{(selected.items || []).map(row => <div key={row.id} className="rounded-lg border border-slate-800 bg-slate-950/35 p-3"><div className="flex flex-wrap items-center gap-2"><span className="rounded border border-slate-700 px-2 py-0.5 text-[10px] uppercase text-slate-400">{row.item_type}</span><span className="break-all font-mono text-xs text-cyan-300">{row.item_key}</span></div>{row.note && <p className="mt-2 text-xs text-slate-400">{row.note}</p>}</div>)}{!selected.items?.length && <p className="text-sm text-slate-500">No evidence has been added yet.</p>}</div></section>

          <section className="panel p-5"><p className="eyebrow">Audit timeline</p><div className="mt-4 space-y-3">{(selected.audit || []).map(event => <div key={event.id} className="border-l border-slate-700 pl-4"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-medium text-white">{event.action.replaceAll('_', ' ')}</p><span className="text-[10px] text-slate-600">{new Date(event.created_at).toLocaleString()}</span></div><p className="mt-1 text-xs text-slate-400">Actor: {event.actor}{event.note ? ` · ${event.note}` : ''}</p></div>)}</div></section>
        </>}
      </div>
    </div>
  </div>;
}
