import { useEffect, useState } from 'react';
import { api } from '../api/client';

const statusOptions = ['open', 'in_progress', 'escalated', 'closed'];
const priorities = ['low', 'medium', 'high', 'critical'];
const cls = 'rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white';
const ETH_ADDR = /^0x[a-fA-F0-9]{40}$/;
const TX_HASH = /^0x[a-fA-F0-9]{64}$/;

export default function CaseManagement() {
  const [cases, setCases] = useState([]);
  const [selected, setSelected] = useState(null);
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('medium');
  const [accessKey, setAccessKey] = useState('');
  const [session, setSession] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [itemType, setItemType] = useState('transaction');
  const [itemKey, setItemKey] = useState('');
  const [evidenceNote, setEvidenceNote] = useState('');
  const [statusReason, setStatusReason] = useState('');
  const [assignee, setAssignee] = useState('');
  const [nextStatus, setNextStatus] = useState('in_progress');

  async function refresh() {
    try {
      const [auth, data] = await Promise.all([api.getAnalystSession(), api.listCases()]);
      setSession(auth); setCases(data.cases || []);
    } catch (e) { setError(e.message || 'Unable to load cases'); }
  }
  useEffect(() => { refresh(); }, []);
  async function loadCase(id) {
    setBusy(true); setError('');
    try { const value = await api.getCase(id); setSelected(value); setNextStatus(value.status); setAssignee(value.assignee || ''); }
    catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function connect(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api.createAnalystSession(accessKey); setAccessKey(''); await refresh(); setNotice('Analyst session established.'); }
    catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function create(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const result = await api.createCase({ title: title.trim(), priority });
      setTitle(''); await refresh(); await loadCase(result.id); setNotice('Case created with an audit record.');
    } catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function addEvidence(e) {
    e.preventDefault(); setBusy(true); setError('');
    const key = itemKey.trim();
    if ((itemType === 'transaction' && !TX_HASH.test(key)) || (itemType === 'address' && !ETH_ADDR.test(key))) {
      setError('Enter a valid Ethereum transaction hash or wallet address.'); setBusy(false); return;
    }
    try { await api.addCaseItem(selected.id, { item_type: itemType, item_key: key, note: evidenceNote.trim() || null }); setItemKey(''); setEvidenceNote(''); await loadCase(selected.id); setNotice('Evidence saved and audit record updated.'); }
    catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function changeStatus(e) {
    e.preventDefault(); if (!statusReason.trim()) { setError('A reason is required for a case status change.'); return; }
    setBusy(true); setError('');
    try { await api.updateCase(selected.id, { status: nextStatus, note: statusReason.trim(), assignee: assignee.trim() || null }); setStatusReason(''); await loadCase(selected.id); await refresh(); setNotice('Status change recorded in the case audit trail.'); }
    catch(e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function downloadReport() {
    setBusy(true); setError('');
    try {
      const report = await api.getCaseReport(selected.id);
      const blob = new Blob([JSON.stringify(report, null, 2)], {type:'application/json'});
      const url = URL.createObjectURL(blob); const a = document.createElement('a');
      a.href = url; a.download = 'chainscope-case-'+selected.id+'.json'; a.click(); URL.revokeObjectURL(url);
    } catch(e) {setError(e.message);}
    finally {setBusy(false);}
  }
  return <div className="space-y-5">
    <div className="panel p-5"><h2 className="text-xl font-semibold text-white">Case management</h2><p className="mt-2 text-sm text-slate-400">Persistent investigations, case evidence, review decisions and exportable evidence-linked reports. Access is role-restricted.</p>
      <div className="mt-4 flex flex-wrap items-center gap-3"><span className="text-sm text-slate-300">Session: {session?.role || 'not authenticated'}</span><button type="button" onClick={refresh} disabled={busy} className="secondary-button">Refresh</button></div>
      <form onSubmit={connect} className="mt-4 flex flex-wrap gap-2"><input type="password" aria-label="Analyst access key" autoComplete="off" value={accessKey} onChange={e=>setAccessKey(e.target.value)} className={cls+' flex-1'} placeholder="Analyst access key (not stored in browser storage)" required/><button disabled={busy} className="primary-button">Unlock analyst actions</button></form>
      {error && <p className="mt-3 text-sm text-rose-300" role="alert">{error}</p>}{notice && <p className="mt-3 text-sm text-emerald-300" role="status">{notice}</p>}
    </div>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <section className="panel p-5"><h3 className="font-semibold text-white">Investigations</h3><form onSubmit={create} className="mt-4 space-y-3"><input className={cls+' w-full'} value={title} onChange={e=>setTitle(e.target.value)} minLength={3} maxLength={240} required placeholder="New case title"/><select className={cls+' w-full'} value={priority} onChange={e=>setPriority(e.target.value)}>{priorities.map(x=><option key={x}>{x}</option>)}</select><button disabled={busy} className="primary-button">Create case</button></form>
        <div className="mt-5 space-y-2">{cases.map(c=><button type="button" key={c.id} onClick={()=>loadCase(c.id)} className={'w-full rounded-lg border p-3 text-left '+(selected?.id===c.id?'border-cyan-500 bg-cyan-950/20':'border-slate-700 bg-slate-900/50')}><span className="block text-sm font-semibold text-white">{c.title}</span><span className="mt-1 block text-xs text-slate-400">{c.status} · {c.priority} · {c.evidence_items || 0} items</span></button>)}{!cases.length&&<p className="text-sm text-slate-400">No accessible cases. Sign in to view your investigation queue.</p>}</div></section>
      <section className="panel p-5">{!selected?<p className="text-slate-400">Select a case to inspect its evidence, audit trail and status.</p>:<div className="space-y-5"><div><h3 className="text-lg font-semibold text-white">{selected.title}</h3><p className="mt-1 break-all font-mono text-xs text-slate-500">{selected.id}</p><p className="mt-2 text-sm text-slate-300">Status: {selected.status} · Priority: {selected.priority} · Assigned: {selected.assignee || 'Unassigned'}</p></div>
        <form onSubmit={addEvidence} className="space-y-2 border-t border-slate-700 pt-4"><h4 className="font-semibold text-white">Attach evidence</h4><select className={cls} value={itemType} onChange={e=>setItemType(e.target.value)}><option value="transaction">Transaction</option><option value="address">Address</option><option value="entity">Entity reference</option></select><input required value={itemKey} onChange={e=>setItemKey(e.target.value)} placeholder="Hash, wallet, or entity reference" className={cls+' w-full'}/><textarea value={evidenceNote} onChange={e=>setEvidenceNote(e.target.value)} placeholder="Evidence note" className={cls+' w-full'} rows={2}/><button className="primary-button" disabled={busy}>Attach evidence</button></form>
        <form onSubmit={changeStatus} className="space-y-2 border-t border-slate-700 pt-4"><h4 className="font-semibold text-white">Update case status</h4><select value={nextStatus} onChange={e=>setNextStatus(e.target.value)} className={cls}>{statusOptions.map(x=><option key={x}>{x}</option>)}</select><input value={assignee} onChange={e=>setAssignee(e.target.value)} maxLength={120} className={cls+" w-full"} placeholder="Assignee (optional)" aria-label="Case assignee"/><textarea value={statusReason} onChange={e=>setStatusReason(e.target.value)} required maxLength={2000} rows={2} className={cls+" w-full"} placeholder="Reason for changing case state" aria-label="Case status change reason"/><p className="text-xs text-slate-400">A distinct written reason is required for every state change, independently of evidence notes.</p><button disabled={busy} className="secondary-button">Save status and audit</button></form>
        <button type="button" disabled={busy} className="secondary-button" onClick={downloadReport}>Export JSON evidence report</button>
        <div><h4 className="font-semibold text-white">Evidence ({selected.items?.length || 0})</h4><div className="mt-2 space-y-2">{(selected.items||[]).map(i=><div key={i.id} className="rounded-lg border border-slate-700 p-3"><p className="text-xs text-cyan-300">{i.item_type}</p><p className="mt-1 break-all font-mono text-xs text-white">{i.item_key}</p>{i.note&&<p className="mt-2 text-xs text-slate-400">{i.note}</p>}</div>)}</div></div>
        <div><h4 className="font-semibold text-white">Audit history</h4><div className="mt-2 max-h-60 space-y-2 overflow-y-auto">{(selected.audit||[]).map(a=><div key={a.id} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300">{a.action} · {a.actor} · {String(a.created_at||'')}{a.note&&<p className="mt-1 text-slate-400">{a.note}</p>}</div>)}</div></div>
      </div>}</section>
    </div>
    <p className="text-xs text-amber-300">Export reports reflect retained evidence only. Missing or expired transactions remain unverified; case status is not a finding of wrongdoing.</p>
  </div>;
}
