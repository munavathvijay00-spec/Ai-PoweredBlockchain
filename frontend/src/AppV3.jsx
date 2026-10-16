import { useState } from 'react';
import App from './App.jsx';
import CaseWorkspace from './components/CaseWorkspace.jsx';
import { api } from './api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';
const eth = wei => {
  try { return (Number(BigInt(String(wei || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 }); }
  catch { return '—'; }
};

function CoverageCard({ coverage, report }) {
  if (!coverage && !report) return null;
  const grade = coverage?.coverage_grade || 'unknown';
  const gradeText = {
    selected_categories_complete: 'Selected categories complete',
    partial_cached_history: 'Partial indexed history',
    retained_monitor_window_only: 'Monitor-window evidence only',
    no_local_evidence: 'No local evidence yet',
  }[grade] || 'Coverage unknown';
  const indexedCount = Number(coverage?.indexed_history_cache?.records || report?.observed_unique_transfers || 0);
  const retainedCount = Number(coverage?.retained_native_transactions?.count || 0);
  return <section className="panel p-5" aria-labelledby="coverage-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="eyebrow">Evidence coverage</p><h2 id="coverage-title" className="mt-2 text-lg font-semibold text-white">What ChainScope actually examined</h2></div>
      <span className="status-pill border-sky-400/20 bg-sky-400/[0.06] text-sky-200">{gradeText}</span>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-3">
      <div className="rounded-lg border border-slate-700 bg-slate-950/30 p-3"><p className="text-xs text-slate-400">Retained native tx</p><p className="mt-1 text-lg font-semibold text-white">{retainedCount.toLocaleString()}</p></div>
      <div className="rounded-lg border border-slate-700 bg-slate-950/30 p-3"><p className="text-xs text-slate-400">Indexed evidence</p><p className="mt-1 text-lg font-semibold text-white">{indexedCount.toLocaleString()}</p></div>
      <div className="rounded-lg border border-slate-700 bg-slate-950/30 p-3"><p className="text-xs text-slate-400">Full EVM history</p><p className="mt-1 text-lg font-semibold text-amber-200">Not claimed</p></div>
    </div>
    <p className="mt-4 text-sm leading-6 text-slate-300">{coverage?.coverage_statement || report?.coverage || 'Coverage is bounded to evidence returned by configured providers and retained data.'}</p>
  </section>;
}

function InvestigationLab({ onSendToCase }) {
  const [address, setAddress] = useState('');
  const [wallet, setWallet] = useState('');
  const [fundFlow, setFundFlow] = useState(null);
  const [copilot, setCopilot] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid Ethereum address.'); return; }
    setLoading(true); setError(''); setFundFlow(null); setCopilot(null); setCoverage(null); setReport(null); setWallet(target.toLowerCase());
    const [flow, ai, coverageResult, reportResult] = await Promise.allSettled([
      api.getFundFlow(target),
      api.getCopilot(target),
      api.getWalletCoverageSummary(target),
      api.getWalletReport(target),
    ]);
    if (flow.status === 'fulfilled') setFundFlow(flow.value);
    if (ai.status === 'fulfilled') setCopilot(ai.value);
    if (coverageResult.status === 'fulfilled') setCoverage(coverageResult.value);
    if (reportResult.status === 'fulfilled') setReport(reportResult.value);

    const usefulLoaded = [flow, coverageResult, reportResult].some(item => item.status === 'fulfilled');
    if (!usefulLoaded) setError('Investigation services are currently unavailable. Try again shortly.');
    else if (flow.status === 'rejected') setError('Indexed evidence loaded, but retained fund-flow is temporarily unavailable.');
    else if (ai.status === 'rejected' && ai.reason?.status !== 401) setError('Evidence loaded. Grounded AI is temporarily unavailable.');
    setLoading(false);
  }

  return <div className="min-h-screen bg-[#0d1628] text-slate-100">
    <main className="platform-shell space-y-5 py-6">
      <section className="panel-strong p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow">Investigation Lab</p><h1 className="mt-2 text-2xl font-semibold text-white">Wallet investigation</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Search one Ethereum wallet to inspect observed flow, indexed transfer evidence, counterparties, entity matches, coverage limits, and grounded findings where authorized.</p></div>
          <span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">Evidence-first</span>
        </div>
        <form onSubmit={investigate} className="mt-5 flex flex-col gap-3 sm:flex-row"><input value={address} onChange={e => setAddress(e.target.value)} className="soft-input min-w-0 flex-1 font-mono" placeholder="0x… Ethereum wallet address" aria-label="Ethereum wallet address" autoComplete="off" spellCheck="false" /><button className="primary-button sm:min-w-44" disabled={loading}>{loading ? 'Investigating…' : 'Run investigation'}</button></form>
        {error && <p role="alert" className="mt-3 text-sm text-amber-200">{error}</p>}
      </section>

      {wallet && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Investigation summary">
        <div className="panel p-4"><p className="eyebrow">Wallet</p><a href={`https://etherscan.io/address/${wallet}`} target="_blank" rel="noreferrer" className="mt-3 block break-all font-mono text-sm text-cyan-300">{short(wallet)} ↗</a></div>
        <div className="panel p-4"><p className="eyebrow">Observed incoming</p><p className="mt-3 text-xl font-semibold text-emerald-300">{fundFlow ? eth(fundFlow.flow_summary?.observed_incoming_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Observed outgoing</p><p className="mt-3 text-xl font-semibold text-amber-200">{fundFlow ? eth(fundFlow.flow_summary?.observed_outgoing_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Grounded AI</p><p className={`mt-3 text-xl font-semibold ${copilot?.grounded ? 'text-emerald-300' : 'text-slate-300'}`}>{copilot ? (copilot.grounded ? 'Verified' : 'Fallback') : 'Protected'}</p></div>
      </section>}

      <CoverageCard coverage={coverage} report={report} />

      {report && <section className="panel p-5" aria-labelledby="indexed-evidence-title">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Provider-indexed evidence</p><h2 id="indexed-evidence-title" className="mt-2 text-lg font-semibold text-white">Transfer evidence snapshot</h2></div><span className="text-sm text-slate-300">{report.observed_unique_transfers || 0} records</span></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="coverage-row"><div><p className="font-medium text-white">Incoming</p><p className="mt-1 text-sm text-slate-300">{report.incoming_count || 0} observed records</p></div></div><div className="coverage-row"><div><p className="font-medium text-white">Outgoing</p><p className="mt-1 text-sm text-slate-300">{report.outgoing_count || 0} observed records</p></div></div><div className="coverage-row"><div><p className="font-medium text-white">Counterparties</p><p className="mt-1 text-sm text-slate-300">{report.unique_counterparties || 0} unique observed</p></div></div></div>
      </section>}

      {fundFlow && <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]">
        <section className="panel p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Directed fund-flow paths</p><h2 className="mt-2 text-lg font-semibold text-white">Observed path evidence</h2></div><span className="text-sm text-slate-300">{fundFlow.directed_paths?.length || 0} paths</span></div>
          <p className="mt-2 text-sm leading-6 text-amber-200">{fundFlow.warning}</p>
          <div className="mt-4 max-h-[620px] space-y-3 overflow-y-auto pr-1">{(fundFlow.directed_paths || []).slice(0, 50).map((path, index) => <div key={`${index}-${path.tx_hashes?.join('-')}`} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><div className="flex flex-wrap items-center gap-2"><span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{path.hop_count} hop{path.hop_count === 1 ? '' : 's'}</span><span className="text-sm text-slate-300">Path floor {eth(path.path_min_value_wei)} ETH</span><span className="text-sm text-slate-300">Max risk {path.max_risk_score}</span></div><div className="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-xs text-slate-300">{(path.addresses || []).map((item, i) => <span key={`${item}-${i}`} className="flex items-center gap-1.5"><a href={`https://etherscan.io/address/${item}`} target="_blank" rel="noreferrer" className="text-cyan-300">{short(item)}</a>{i < path.addresses.length - 1 && <span aria-hidden="true">→</span>}</span>)}</div><div className="mt-3 flex flex-wrap gap-2">{(path.tx_hashes || []).map(hash => <a key={hash} href={`https://etherscan.io/tx/${hash}`} target="_blank" rel="noreferrer" className="text-xs text-sky-300 underline">Verify tx {short(hash)} ↗</a>)}</div></div>)}</div>
        </section>

        <div className="space-y-5">
          <section className="panel p-5"><p className="eyebrow">Entity exposure</p><div className="mt-4 space-y-3">{(fundFlow.entity_exposures || []).map((exposure, index) => <div key={`${exposure.destination}-${index}`} className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><a href={`https://etherscan.io/address/${exposure.destination}`} target="_blank" rel="noreferrer" className="break-all font-mono text-sm text-emerald-300">{short(exposure.destination)} ↗</a><p className="mt-1 text-sm text-slate-300">{exposure.hop_count} hops · path floor {eth(exposure.path_min_value_wei)} ETH</p>{(exposure.entity_labels || []).map((label, i) => <p key={i} className="mt-2 text-sm text-white">{label.entity_name || label.entity_id} <span className="text-slate-300">· {label.source} · confidence {label.confidence ?? '—'}</span></p>)}</div>)}{!fundFlow.entity_exposures?.length && <p className="text-sm text-slate-300">No source-attributed entity exposure was found in this bounded path set.</p>}</div></section>
          <section className="panel p-5"><p className="eyebrow">Top counterparties</p><div className="mt-4 space-y-3">{(fundFlow.top_counterparties || []).slice(0, 10).map(row => <div key={row.address} className="flex flex-col gap-1 border-b border-slate-700/70 pb-3 text-sm sm:flex-row sm:items-center sm:justify-between"><a href={`https://etherscan.io/address/${row.address}`} target="_blank" rel="noreferrer" className="break-all font-mono text-cyan-300">{short(row.address)}</a><span className="text-slate-300">{row.tx_count} tx · {eth(row.total_wei)} ETH</span></div>)}</div></section>
        </div>
      </div>}

      {copilot && <section className="panel-strong p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">AI Investigation Copilot</p><h2 className="mt-2 text-lg font-semibold text-white">Cited findings</h2></div><div className="flex flex-wrap gap-2"><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-200">{copilot.mode || 'deterministic'}</span><span className={`status-pill ${copilot.grounded ? 'border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200' : 'border-amber-400/20 bg-amber-400/[0.06] text-amber-200'}`}>{copilot.grounded ? 'grounded' : 'fallback'}</span></div></div>
        <p className="mt-2 text-sm text-slate-300">Records examined: {copilot.coverage?.records_examined ?? 0}. Full-chain completeness is not claimed.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">{(copilot.claims || []).map((claim, index) => <article key={index} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><p className="text-sm leading-6 text-slate-100">{claim.text}</p><div className="mt-3 flex flex-wrap gap-2">{(claim.finding_ids || []).map(id => <span key={id} className="rounded border border-violet-400/20 bg-violet-400/[0.05] px-2 py-1 font-mono text-xs text-violet-200">{id}</span>)}</div>{(claim.citations || []).flatMap(citation => citation.evidence_urls || []).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="mt-2 mr-3 inline-block text-xs text-sky-300 underline">Verify transaction ↗</a>)}</article>)}</div>
        {copilot.uncertainty && <p className="mt-5 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-4 py-3 text-sm leading-6 text-amber-100">Uncertainty: {copilot.uncertainty}</p>}
      </section>}

      {wallet && <section className="panel flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="eyebrow">Continue investigation</p><p className="mt-2 text-sm text-slate-300">Move this wallet directly into case management without retyping the address.</p></div><button type="button" onClick={() => onSendToCase(wallet)} className="secondary-button">Add wallet to a case</button></section>}
    </main>
  </div>;
}

export default function AppV3() {
  const [workspace, setWorkspace] = useState('platform');
  const [caseEvidence, setCaseEvidence] = useState(null);
  function sendWalletToCase(address) {
    setCaseEvidence({ item_type: 'address', item_key: address, note: 'Added from Investigation Lab.' });
    setWorkspace('cases');
  }
  return <div className="min-h-screen bg-[#0d1628]">
    <div className="sticky top-0 z-[80] border-b border-slate-800 bg-[#09111f]/95 px-3 py-2 backdrop-blur">
      <div className="mx-auto flex max-w-[1540px] flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><span className="text-sm font-semibold tracking-[0.15em] text-cyan-300">CHAINSCOPE</span><span className="hidden text-xs text-slate-400 sm:inline">Investigation OS</span></div>
        <nav className="flex max-w-full gap-1 overflow-x-auto" aria-label="Product workspace"><button onClick={() => setWorkspace('platform')} aria-current={workspace === 'platform' ? 'page' : undefined} className={`workspace-chip ${workspace === 'platform' ? 'workspace-chip-active' : ''}`}>Monitor</button><button onClick={() => setWorkspace('lab')} aria-current={workspace === 'lab' ? 'page' : undefined} className={`workspace-chip ${workspace === 'lab' ? 'workspace-chip-active' : ''}`}>Investigation Lab</button><button onClick={() => setWorkspace('cases')} aria-current={workspace === 'cases' ? 'page' : undefined} className={`workspace-chip ${workspace === 'cases' ? 'workspace-chip-active' : ''}`}>Cases</button></nav>
      </div>
    </div>
    {workspace === 'platform' && <App />}
    {workspace === 'lab' && <InvestigationLab onSendToCase={sendWalletToCase} />}
    {workspace === 'cases' && <div className="min-h-screen bg-[#0d1628] text-slate-100"><main className="platform-shell py-6"><CaseWorkspace initialEvidence={caseEvidence} onEvidenceConsumed={() => setCaseEvidence(null)} /></main></div>}
  </div>;
}
