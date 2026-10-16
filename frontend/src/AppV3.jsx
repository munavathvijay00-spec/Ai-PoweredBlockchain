import { useState } from 'react';
import App from './App.jsx';
import CaseWorkspace from './components/CaseWorkspace.jsx';
import { api, hasAnalystCredential, setAnalystCredential } from './api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';
const eth = wei => {
  try { return (Number(BigInt(String(wei || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 }); }
  catch { return '—'; }
};

function InvestigationLab() {
  const [address, setAddress] = useState('');
  const [wallet, setWallet] = useState('');
  const [fundFlow, setFundFlow] = useState(null);
  const [copilot, setCopilot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [credential, setCredential] = useState('');
  const [unlocked, setUnlocked] = useState(hasAnalystCredential());

  function unlock(event) {
    event.preventDefault(); setAnalystCredential(credential); setCredential(''); setUnlocked(hasAnalystCredential());
  }

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid Ethereum address.'); return; }
    setLoading(true); setError(''); setFundFlow(null); setCopilot(null); setWallet(target.toLowerCase());
    const [flow, ai] = await Promise.allSettled([api.getFundFlow(target), api.getCopilot(target)]);
    if (flow.status === 'fulfilled') setFundFlow(flow.value);
    if (ai.status === 'fulfilled') setCopilot(ai.value);
    if (flow.status === 'rejected' && ai.status === 'rejected') setError(ai.reason?.status === 401 ? 'Unlock analyst/viewer access before running the investigation copilot.' : 'Investigation services are currently unavailable.');
    else if (ai.status === 'rejected') setError('Fund-flow loaded, but Copilot is locked or unavailable.');
    else if (flow.status === 'rejected') setError('Copilot loaded, but fund-flow evidence is unavailable.');
    setLoading(false);
  }

  return <div className="min-h-screen bg-[#0d1628] text-slate-100">
    <main className="platform-shell space-y-5 py-6">
      <section className="panel-strong p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow">Investigation Lab</p><h1 className="mt-2 text-2xl font-semibold text-white">Fund-flow + grounded AI Copilot</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Trace bounded native-ETH paths, inspect entity exposure, quantify observed flow, and generate claim-level AI findings that link back to deterministic evidence.</p></div>
          <span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-300">Evidence-first</span>
        </div>
        {!unlocked && <form onSubmit={unlock} className="mt-5 flex max-w-2xl flex-col gap-2 sm:flex-row"><input type="password" value={credential} onChange={e => setCredential(e.target.value)} className="soft-input flex-1" placeholder="Viewer/analyst key for Copilot" aria-label="Viewer or analyst access key" /><button className="secondary-button" disabled={!credential.trim()}>Unlock AI</button></form>}
        {unlocked && <div className="mt-4 flex items-center gap-3 text-xs text-emerald-300"><span>● Analyst/viewer session unlocked</span><button onClick={() => { setAnalystCredential(''); setUnlocked(false); }} className="text-slate-500 underline">lock</button></div>}
        <form onSubmit={investigate} className="mt-5 flex flex-col gap-3 sm:flex-row"><input value={address} onChange={e => setAddress(e.target.value)} className="soft-input flex-1 font-mono" placeholder="0x… Ethereum wallet address" aria-label="Ethereum wallet address" /><button className="primary-button min-w-44" disabled={loading}>{loading ? 'Investigating…' : 'Run investigation'}</button></form>
        {error && <p role="alert" className="mt-3 text-sm text-amber-300">{error}</p>}
      </section>

      {wallet && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="panel p-4"><p className="eyebrow">Wallet</p><a href={`https://etherscan.io/address/${wallet}`} target="_blank" rel="noreferrer" className="mt-3 block font-mono text-sm text-cyan-300">{short(wallet)} ↗</a></div>
        <div className="panel p-4"><p className="eyebrow">Observed incoming</p><p className="mt-3 text-xl font-semibold text-emerald-300">{fundFlow ? eth(fundFlow.flow_summary?.observed_incoming_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Observed outgoing</p><p className="mt-3 text-xl font-semibold text-amber-300">{fundFlow ? eth(fundFlow.flow_summary?.observed_outgoing_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Grounded AI</p><p className={`mt-3 text-xl font-semibold ${copilot?.grounded ? 'text-emerald-300' : 'text-slate-500'}`}>{copilot ? (copilot.grounded ? 'Verified' : 'Fallback') : '—'}</p></div>
      </section>}

      {fundFlow && <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,.75fr)]">
        <section className="panel p-5">
          <div className="flex items-start justify-between gap-3"><div><p className="eyebrow">Directed fund-flow paths</p><h2 className="mt-2 text-lg font-semibold text-white">Observed path evidence</h2></div><span className="text-xs text-slate-500">{fundFlow.directed_paths?.length || 0} paths</span></div>
          <p className="mt-2 text-xs leading-5 text-amber-300">{fundFlow.warning}</p>
          <div className="mt-4 max-h-[620px] space-y-3 overflow-y-auto pr-1">{(fundFlow.directed_paths || []).slice(0, 50).map((path, index) => <div key={`${index}-${path.tx_hashes?.join('-')}`} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><div className="flex flex-wrap items-center gap-2"><span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-300">{path.hop_count} hop{path.hop_count === 1 ? '' : 's'}</span><span className="text-xs text-slate-500">conservative path value {eth(path.path_min_value_wei)} ETH</span><span className="text-xs text-slate-500">max risk {path.max_risk_score}</span></div><div className="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-slate-400">{(path.addresses || []).map((item, i) => <span key={`${item}-${i}`} className="flex items-center gap-1.5"><a href={`https://etherscan.io/address/${item}`} target="_blank" rel="noreferrer" className="text-cyan-300">{short(item)}</a>{i < path.addresses.length - 1 && <span>→</span>}</span>)}</div><div className="mt-3 flex flex-wrap gap-2">{(path.tx_hashes || []).map(hash => <a key={hash} href={`https://etherscan.io/tx/${hash}`} target="_blank" rel="noreferrer" className="text-[10px] text-sky-300 underline">{short(hash)} ↗</a>)}</div></div>)}</div>
        </section>

        <div className="space-y-5">
          <section className="panel p-5"><p className="eyebrow">Entity exposure</p><div className="mt-4 space-y-3">{(fundFlow.entity_exposures || []).map((exposure, index) => <div key={`${exposure.destination}-${index}`} className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><a href={`https://etherscan.io/address/${exposure.destination}`} target="_blank" rel="noreferrer" className="font-mono text-xs text-emerald-300">{short(exposure.destination)} ↗</a><p className="mt-1 text-xs text-slate-400">{exposure.hop_count} hops · {eth(exposure.path_min_value_wei)} ETH conservative path value</p>{(exposure.entity_labels || []).map((label, i) => <p key={i} className="mt-2 text-xs text-white">{label.entity_name || label.entity_id} <span className="text-slate-500">· {label.source} · confidence {label.confidence ?? '—'}</span></p>)}</div>)}{!fundFlow.entity_exposures?.length && <p className="text-sm text-slate-500">No source-attributed entity exposure was found in the bounded path set.</p>}</div></section>
          <section className="panel p-5"><p className="eyebrow">Top counterparties</p><div className="mt-4 space-y-2">{(fundFlow.top_counterparties || []).slice(0, 10).map(row => <div key={row.address} className="flex items-center justify-between gap-3 border-b border-slate-800/70 pb-2 text-xs"><a href={`https://etherscan.io/address/${row.address}`} target="_blank" rel="noreferrer" className="font-mono text-cyan-300">{short(row.address)}</a><span className="text-slate-400">{row.tx_count} tx · {eth(row.total_wei)} ETH</span></div>)}</div></section>
        </div>
      </div>}

      {copilot && <section className="panel-strong p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">AI Investigation Copilot</p><h2 className="mt-2 text-lg font-semibold text-white">Cited findings</h2></div><div className="flex gap-2"><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-300">{copilot.mode || 'deterministic'}</span><span className={`status-pill ${copilot.grounded ? 'border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-300' : 'border-amber-400/20 bg-amber-400/[0.06] text-amber-300'}`}>{copilot.grounded ? 'grounded' : 'fallback'}</span></div></div>
        <p className="mt-2 text-xs text-slate-500">Records examined: {copilot.coverage?.records_examined ?? 0}. Full-chain completeness is not claimed.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">{(copilot.claims || []).map((claim, index) => <article key={index} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><p className="text-sm leading-6 text-slate-200">{claim.text}</p><div className="mt-3 flex flex-wrap gap-2">{(claim.finding_ids || []).map(id => <span key={id} className="rounded border border-violet-400/20 bg-violet-400/[0.05] px-2 py-1 font-mono text-[10px] text-violet-300">{id}</span>)}</div>{(claim.citations || []).flatMap(citation => citation.evidence_urls || []).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="mt-2 mr-3 inline-block text-[10px] text-sky-300 underline">Verify transaction ↗</a>)}</article>)}</div>
        {copilot.uncertainty && <p className="mt-5 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-4 py-3 text-xs leading-5 text-amber-200">Uncertainty: {copilot.uncertainty}</p>}
      </section>}
    </main>
  </div>;
}

export default function AppV3() {
  const [workspace, setWorkspace] = useState('platform');
  return <div className="min-h-screen bg-[#0d1628]">
    <div className="sticky top-0 z-[80] border-b border-slate-800 bg-[#09111f]/95 px-3 py-2 backdrop-blur">
      <div className="mx-auto flex max-w-[1540px] items-center justify-between gap-3">
        <div className="flex items-center gap-2"><span className="text-xs font-semibold tracking-[0.15em] text-cyan-300">CHAINSCOPE</span><span className="hidden text-[10px] text-slate-600 sm:inline">Investigation OS</span></div>
        <nav className="flex gap-1" aria-label="Product workspace"><button onClick={() => setWorkspace('platform')} className={`workspace-chip ${workspace === 'platform' ? 'workspace-chip-active' : ''}`}>Monitor</button><button onClick={() => setWorkspace('lab')} className={`workspace-chip ${workspace === 'lab' ? 'workspace-chip-active' : ''}`}>Investigation Lab</button><button onClick={() => setWorkspace('cases')} className={`workspace-chip ${workspace === 'cases' ? 'workspace-chip-active' : ''}`}>Cases</button></nav>
      </div>
    </div>
    {workspace === 'platform' && <App />}
    {workspace === 'lab' && <InvestigationLab />}
    {workspace === 'cases' && <div className="min-h-screen bg-[#0d1628] text-slate-100"><main className="platform-shell py-6"><CaseWorkspace /></main></div>}
  </div>;
}
