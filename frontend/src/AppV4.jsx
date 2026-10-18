import { lazy, Suspense, useMemo, useState } from 'react';
const App = lazy(() => import('./App.jsx'));
const CaseWorkspace = lazy(() => import('./components/CaseWorkspace.jsx'));
const UnifiedInvestigationGraph = lazy(() => import('./components/UnifiedInvestigationGraph.jsx'));

import { api } from './api/client';
import TransactionSemanticEvidence from './components/TransactionSemanticEvidence.jsx';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';
const eth = wei => {
  try { return (Number(BigInt(String(wei || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 }); }
  catch { return '—'; }
};
const amount = value => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value ?? '—');
};

function WorkflowRail({ ready, onCase }) {
  const sections = [
    ['Summary', '#brief-title'], ['Leads', '#explainable-findings-title'],
    ['Graph', '#unified-graph-title'], ['Timeline', '#semantic-title'],
    ['Evidence', '#token-explorer-title'], ['Report', '#findings-title'],
  ];
  return <nav className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Investigation sections">
    {sections.map(([label, target]) => <a key={label} href={target} className="rounded-lg border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs font-medium text-slate-200 hover:border-cyan-400/40 hover:text-cyan-200">{label}</a>)}
    {ready && <button type="button" onClick={onCase} className="secondary-button ml-auto py-2 text-xs">Add to case</button>}
  </nav>;
}

function IntelligenceBrief({ wallet, flow, report, coverage, copilot }) {
  const paths = flow?.directed_paths || [];
  const highest = [...paths].sort((a, b) => Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0))[0];
  const assets = flow?.token_flow?.assets || [];
  const exposures = flow?.entity_exposures || [];
  const signals = report?.behavioral_signals || [];
  const observations = [
    { label: 'Highest path risk', value: highest ? String(highest.max_risk_score ?? 0) : '—', detail: highest ? `${highest.hop_count} hop · ${eth(highest.path_min_value_wei)} ETH path floor` : 'No directed native path loaded' },
    { label: 'Observed counterparties', value: String(flow?.top_counterparties?.length || report?.unique_counterparties || 0), detail: 'Within currently loaded evidence' },
    { label: 'ERC-20 assets', value: String(assets.length), detail: `${flow?.token_flow?.records_examined || 0} indexed token records examined` },
    { label: 'Labeled path exposure', value: String(exposures.length), detail: 'Exact source-attributed matches reached by bounded paths' },
  ];
  return <section className="panel-strong p-5 sm:p-6" aria-labelledby="brief-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="eyebrow text-cyan-300">Intelligence brief</p><h2 id="brief-title" className="mt-2 text-xl font-semibold text-white">What matters first</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Prioritized deterministic observations from loaded evidence. These are investigation leads, not accusations.</p></div>
      <span className="status-pill border-sky-400/20 bg-sky-400/[0.06] text-sky-200">{coverage?.coverage_grade?.replaceAll('_', ' ') || 'Coverage bounded'}</span>
    </div>
    <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{observations.map(item => <div key={item.label} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><p className="text-xs text-slate-400">{item.label}</p><p className="mt-2 text-2xl font-semibold text-white">{item.value}</p><p className="mt-2 text-xs leading-5 text-slate-400">{item.detail}</p></div>)}</div>
    <div className="mt-4 grid gap-3 lg:grid-cols-[1.1fr_.9fr]">
      <div className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Observed behavior</p><div className="mt-3 space-y-2 text-sm text-slate-200"><p>• Native flow: {flow ? `${eth(flow.flow_summary?.observed_incoming_wei)} ETH in · ${eth(flow.flow_summary?.observed_outgoing_wei)} ETH out` : 'unavailable'}.</p><p>• Deterministic signals: {signals.length}.</p><p>• Grounded AI claims: {copilot?.claims?.length || 0}.</p><p>• Wallet: <span className="font-mono text-slate-300">{short(wallet)}</span>.</p></div></div>
      <div className="rounded-xl border border-amber-400/15 bg-amber-400/[0.035] p-4"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-200">Confidence guardrail</p><p className="mt-3 text-sm leading-6 text-slate-300">{coverage?.coverage_statement || report?.coverage || 'Evidence is bounded to retained native transfers and provider-indexed wallet evidence.'}</p><p className="mt-3 text-xs leading-5 text-amber-100">No result is complete wallet history, beneficial ownership proof, taint proof, or a fraud verdict.</p></div>
    </div>
  </section>;
}

function AssetIntelligence({ tokenFlow }) {
  if (!tokenFlow?.available) return null;
  const assets = tokenFlow.assets || [];
  return <section className="panel p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Asset intelligence</p><h2 className="mt-2 text-lg font-semibold text-white">ERC-20 / stablecoin movement</h2><p className="mt-2 text-sm leading-6 text-slate-400">Token evidence stays separate from native ETH so cross-asset values are never falsely treated as conserved flow.</p></div><span className="text-sm text-slate-300">{tokenFlow.records_examined || 0} records</span></div>
    {assets.length ? <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800" role="region" tabIndex={0} aria-label="Token movement"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-slate-950/70 text-xs text-slate-500"><tr><th className="px-4 py-3">Asset</th><th className="px-4 py-3">Incoming</th><th className="px-4 py-3">Outgoing</th><th className="px-4 py-3">Net observed</th><th className="px-4 py-3">Transfers</th><th className="px-4 py-3">Peers</th></tr></thead><tbody>{assets.slice(0, 15).map((asset, index) => <tr key={`${asset.contract_address || asset.asset}-${index}`} className="border-t border-slate-800/80"><td className="px-4 py-3"><p className="font-semibold text-white">{asset.asset}</p>{asset.contract_address && <a href={`https://etherscan.io/token/${asset.contract_address}`} target="_blank" rel="noreferrer" className="mt-1 block font-mono text-xs text-cyan-300">{short(asset.contract_address)} ↗</a>}</td><td className="px-4 py-3 text-emerald-300">{amount(asset.incoming_amount)}</td><td className="px-4 py-3 text-amber-200">{amount(asset.outgoing_amount)}</td><td className="px-4 py-3 text-slate-200">{amount(asset.net_amount)}</td><td className="px-4 py-3 text-slate-300">{Number(asset.incoming_transfer_count || 0) + Number(asset.outgoing_transfer_count || 0)}</td><td className="px-4 py-3 text-slate-300">{asset.unique_counterparties || 0}</td></tr>)}</tbody></table></div> : <p className="mt-4 text-sm text-slate-400">No cached ERC-20 transfers were observed.</p>}
  </section>;
}

function Findings({ report, copilot }) {
  const signals = report?.behavioral_signals || [];
  const claims = copilot?.claims || [];
  if (!signals.length && !copilot) return null;
  return <section className="space-y-5">
    {signals.length > 0 && <div className="panel p-5"><p className="eyebrow">Deterministic findings</p><h2 className="mt-2 text-lg font-semibold text-white">Behavior requiring review</h2><div className="mt-4 grid gap-3 lg:grid-cols-2">{signals.map((signal, index) => <article key={`${signal.code}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><p className="font-medium text-white">{signal.title || signal.code}</p><p className="mt-2 text-sm leading-6 text-slate-400">{signal.explanation}</p><div className="mt-3 flex flex-wrap gap-2">{(signal.evidence || []).slice(0, 5).map(item => <a key={item.tx_hash} href={item.url || `https://etherscan.io/tx/${item.tx_hash}`} target="_blank" rel="noreferrer" className="text-xs text-cyan-300 underline">Verify {short(item.tx_hash)} ↗</a>)}</div></article>)}</div></div>}
    {copilot && <div className="panel-strong p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Grounded AI</p><h2 className="mt-2 text-lg font-semibold text-white">Claims tied to evidence</h2></div><span className={`status-pill ${copilot.grounded ? 'border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200' : 'border-amber-400/20 bg-amber-400/[0.06] text-amber-200'}`}>{copilot.grounded ? 'grounded' : 'fallback'}</span></div><div className="mt-5 grid gap-4 lg:grid-cols-2">{claims.map((claim, index) => <article key={index} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><p className="text-sm leading-6 text-slate-100">{claim.text}</p><div className="mt-3 flex flex-wrap gap-2">{(claim.finding_ids || []).map(id => <span key={id} className="rounded border border-violet-400/20 bg-violet-400/[0.05] px-2 py-1 font-mono text-xs text-violet-200">{id}</span>)}</div>{(claim.citations || []).flatMap(citation => citation.evidence_urls || []).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="mt-2 mr-3 inline-block text-xs text-sky-300 underline">Verify transaction ↗</a>)}</article>)}</div>{copilot.uncertainty && <p className="mt-5 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-4 py-3 text-sm leading-6 text-amber-100">Uncertainty: {copilot.uncertainty}</p>}</div>}
  </section>;
}

function Investigation({ onSendToCase }) {
  const [address, setAddress] = useState('');
  const [wallet, setWallet] = useState('');
  const [flow, setFlow] = useState(null);
  const [report, setReport] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [copilot, setCopilot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const caseNote = useMemo(() => {
    if (!wallet) return '';
    const highest = [...(flow?.directed_paths || [])].sort((a, b) => Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0))[0];
    return [
      'Added from canonical ChainScope investigation.',
      `Native flow: ${eth(flow?.flow_summary?.observed_incoming_wei)} ETH in / ${eth(flow?.flow_summary?.observed_outgoing_wei)} ETH out.`,
      `Observed counterparties: ${flow?.top_counterparties?.length || report?.unique_counterparties || 0}.`,
      `ERC-20 assets: ${flow?.token_flow?.assets?.length || 0}.`,
      `Entity path exposures: ${flow?.entity_exposures?.length || 0}.`,
      `Grounded AI claims: ${copilot?.claims?.length || 0}.`,
      highest ? `Highest observed path risk: ${highest.max_risk_score} over ${highest.hop_count} hop(s).` : '',
      'Coverage is bounded; this is not a fraud, ownership, or taint conclusion.',
    ].filter(Boolean).join(' ');
  }, [wallet, flow, report, copilot]);

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid Ethereum address.'); return; }
    setLoading(true); setError(''); setWallet(target.toLowerCase()); setFlow(null); setReport(null); setCoverage(null); setCopilot(null);
    const [flowResult, reportResult, coverageResult, aiResult] = await Promise.allSettled([
      api.getFundFlow(target), api.getWalletReport(target), api.getWalletCoverageSummary(target), api.getCopilot(target),
    ]);
    if (flowResult.status === 'fulfilled') setFlow(flowResult.value);
    if (reportResult.status === 'fulfilled') setReport(reportResult.value);
    if (coverageResult.status === 'fulfilled') setCoverage(coverageResult.value);
    if (aiResult.status === 'fulfilled') setCopilot(aiResult.value);
    if (![flowResult, reportResult, coverageResult].some(result => result.status === 'fulfilled')) setError('Investigation services are temporarily unavailable.');
    else if (flowResult.status === 'rejected') setError('Indexed evidence loaded, but native fund-flow is temporarily unavailable.');
    else if (aiResult.status === 'rejected' && aiResult.reason?.status !== 401) setError('Core evidence loaded. Grounded AI is temporarily unavailable.');
    setLoading(false);
  }

  const sendCase = () => wallet && onSendToCase(wallet, caseNote);
  return <div className="min-h-screen bg-[#0d1628] text-slate-100"><main className="platform-shell space-y-5 py-6">
    <section className="panel-strong p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="eyebrow">Investigation</p><h1 className="mt-2 text-2xl font-semibold text-white">One wallet. One evidence trail.</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Search once, understand the wallet, explore the graph, review findings, and preserve the evidence in a case.</p></div><span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">Evidence-first</span></div><form onSubmit={investigate} className="mt-5 flex flex-col gap-3 sm:flex-row"><input value={address} onChange={event => setAddress(event.target.value)} className="soft-input min-w-0 flex-1 font-mono" placeholder="0x… Ethereum wallet address" aria-label="Ethereum wallet address" autoComplete="off" spellCheck="false" /><button className="primary-button sm:min-w-44" disabled={loading}>{loading ? 'Building intelligence…' : 'Investigate wallet'}</button></form>{error && <p role="alert" className="mt-3 text-sm text-amber-200">{error}</p>}</section>
    <WorkflowRail ready={Boolean(wallet)} onCase={sendCase} />
    {wallet && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Investigation summary"><div className="panel p-4"><p className="eyebrow">Wallet</p><a href={`https://etherscan.io/address/${wallet}`} target="_blank" rel="noreferrer" className="mt-3 block font-mono text-sm text-cyan-300">{short(wallet)} ↗</a></div><div className="panel p-4"><p className="eyebrow">Native in</p><p className="mt-3 text-xl font-semibold text-emerald-300">{flow ? eth(flow.flow_summary?.observed_incoming_wei) : '—'} ETH</p></div><div className="panel p-4"><p className="eyebrow">Native out</p><p className="mt-3 text-xl font-semibold text-amber-200">{flow ? eth(flow.flow_summary?.observed_outgoing_wei) : '—'} ETH</p></div><div className="panel p-4"><p className="eyebrow">Token assets</p><p className="mt-3 text-xl font-semibold text-violet-200">{flow?.token_flow?.assets?.length ?? '—'}</p></div><div className="panel p-4"><p className="eyebrow">AI findings</p><p className="mt-3 text-xl font-semibold text-slate-100">{copilot?.claims?.length || 0}</p></div></section>}
    {wallet && <IntelligenceBrief wallet={wallet} flow={flow} report={report} coverage={coverage} copilot={copilot} />}
    {wallet && <Suspense fallback={<div className="panel p-6" role="status">Loading investigation graph…</div>}><UnifiedInvestigationGraph wallet={wallet} fundFlow={flow} /></Suspense>}
    {flow && <TransactionSemanticEvidence findings={flow.transaction_semantics || []} />}

    <Findings report={report} copilot={copilot} />
    {wallet && <section className="panel-strong flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="eyebrow text-cyan-300">Preserve evidence</p><h2 className="mt-2 text-lg font-semibold text-white">Continue in a case</h2><p className="mt-2 max-w-2xl text-sm text-slate-300">Carry the investigated wallet and evidence summary directly into Case Management.</p></div><button type="button" onClick={sendCase} className="primary-button whitespace-nowrap">Add investigation to case</button></section>}
  </main></div>;
}

export default function AppV4() {
  const [workspace, setWorkspace] = useState('investigate');
  const [caseEvidence, setCaseEvidence] = useState(null);
  function sendWalletToCase(address, note) {
    setCaseEvidence({ item_type: 'address', item_key: address, note });
    setWorkspace('cases');
  }
  return <div className="min-h-screen bg-[#0d1628]">
    <div className="sticky top-0 z-[80] border-b border-slate-800 bg-[#09111f]/95 px-3 py-2 backdrop-blur"><div className="mx-auto flex max-w-[1540px] flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><span className="text-sm font-semibold tracking-[0.15em] text-cyan-300">CHAINSCOPE</span><span className="hidden text-xs text-slate-400 sm:inline">Investigation OS</span></div><nav className="flex max-w-full gap-1 overflow-x-auto" aria-label="Product workspace"><button onClick={() => setWorkspace('investigate')} aria-current={workspace === 'investigate' ? 'page' : undefined} className={`workspace-chip ${workspace === 'investigate' ? 'workspace-chip-active' : ''}`}>Investigate</button><button onClick={() => setWorkspace('monitor')} aria-current={workspace === 'monitor' ? 'page' : undefined} className={`workspace-chip ${workspace === 'monitor' ? 'workspace-chip-active' : ''}`}>Monitor</button><button onClick={() => setWorkspace('cases')} aria-current={workspace === 'cases' ? 'page' : undefined} className={`workspace-chip ${workspace === 'cases' ? 'workspace-chip-active' : ''}`}>Cases</button></nav></div></div>
    {workspace === 'investigate' && <Investigation onSendToCase={sendWalletToCase} />}
    {workspace === 'monitor' && <Suspense fallback={<div className="platform-shell py-8" role="status">Loading Monitor…</div>}><App /></Suspense>}
    {workspace === 'cases' && <div className="min-h-screen bg-[#0d1628] text-slate-100"><main className="platform-shell py-6"><Suspense fallback={<div className="panel p-6" role="status">Loading case workspace…</div>}><CaseWorkspace initialEvidence={caseEvidence} onEvidenceConsumed={() => setCaseEvidence(null)} /></Suspense></main></div>}
  </div>;
}
