import { useMemo, useState } from 'react';
import App from './App.jsx';
import CaseWorkspace from './components/CaseWorkspace.jsx';
import { api } from './api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';
const eth = wei => {
  try { return (Number(BigInt(String(wei || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 }); }
  catch { return '—'; }
};
const tokenAmount = value => {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? '—');
  return number.toLocaleString(undefined, { maximumFractionDigits: 6 });
};

function CoverageBadge({ coverage }) {
  const grade = coverage?.coverage_grade || 'unknown';
  const labels = {
    selected_categories_complete: 'Selected categories complete',
    partial_cached_history: 'Partial indexed history',
    retained_monitor_window_only: 'Monitor-window evidence',
    no_local_evidence: 'No local evidence',
  };
  return <span className="status-pill border-sky-400/20 bg-sky-400/[0.06] text-sky-200">{labels[grade] || 'Coverage bounded'}</span>;
}

function WorkflowRail({ hasResult, onAddCase }) {
  const steps = [
    ['1', 'Search'], ['2', 'Brief'], ['3', 'Flows'], ['4', 'Findings'], ['5', 'Case'],
  ];
  return <div className="panel overflow-x-auto p-3" aria-label="Investigation workflow">
    <div className="flex min-w-[620px] items-center gap-2">
      {steps.map(([number, label], index) => <div key={label} className="flex flex-1 items-center gap-2">
        <div className={`flex min-w-0 flex-1 items-center gap-2 rounded-lg border px-3 py-2 ${hasResult || index === 0 ? 'border-cyan-400/20 bg-cyan-400/[0.04]' : 'border-slate-800 bg-slate-950/25'}`}>
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-slate-600 text-[11px] text-slate-300">{number}</span>
          <span className="truncate text-xs font-medium text-slate-200">{label}</span>
        </div>
        {index < steps.length - 1 && <span className="text-slate-600">→</span>}
      </div>)}
      {hasResult && <button type="button" onClick={onAddCase} className="secondary-button ml-2 whitespace-nowrap py-2 text-xs">Add to case</button>}
    </div>
  </div>;
}

function IntelligenceBrief({ wallet, fundFlow, report, coverage, copilot }) {
  const paths = fundFlow?.directed_paths || [];
  const exposures = fundFlow?.entity_exposures || [];
  const tokenAssets = fundFlow?.token_flow?.assets || [];
  const signals = report?.behavioral_signals || [];
  const motifs = fundFlow?.motifs || {};
  const highestRiskPath = [...paths].sort((a, b) => Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0))[0];
  const maxRisk = Number(highestRiskPath?.max_risk_score || 0);
  const fanOut = (motifs.fan_out || [])[0];
  const fanIn = (motifs.fan_in || [])[0];
  const reciprocalCount = (motifs.reciprocal_pairs || []).length;

  const observations = [];
  if (highestRiskPath) observations.push({ label: 'Highest observed path risk', value: String(maxRisk), detail: `${highestRiskPath.hop_count} hop path · ${eth(highestRiskPath.path_min_value_wei)} ETH path floor` });
  if (exposures.length) observations.push({ label: 'Labeled entity exposure', value: String(exposures.length), detail: 'Source-attributed exact-address matches reached by bounded paths' });
  if (tokenAssets.length) observations.push({ label: 'ERC-20 assets observed', value: String(tokenAssets.length), detail: `${fundFlow?.token_flow?.records_examined || 0} indexed token-transfer records examined` });
  if (fanOut) observations.push({ label: 'Fan-out pattern', value: String(fanOut.edge_count), detail: `Observed outgoing edges from ${short(fanOut.address)}` });
  else if (fanIn) observations.push({ label: 'Fan-in pattern', value: String(fanIn.edge_count), detail: `Observed incoming edges to ${short(fanIn.address)}` });
  else if (reciprocalCount) observations.push({ label: 'Reciprocal relationships', value: String(reciprocalCount), detail: 'Observed address pairs transferred in both directions' });
  if (!observations.length) observations.push({ label: 'Observed review signals', value: String(signals.length), detail: 'No strong path, entity, token, or motif observation in the loaded evidence' });

  return <section className="panel-strong p-5 sm:p-6" aria-labelledby="brief-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow text-cyan-300">Intelligence brief</p>
        <h2 id="brief-title" className="mt-2 text-xl font-semibold text-white">What matters first</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">A deterministic summary of the strongest observations in the loaded evidence. These are investigation priorities, not accusations or ownership conclusions.</p>
      </div>
      <CoverageBadge coverage={coverage} />
    </div>

    <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {observations.slice(0, 4).map(item => <div key={item.label} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4">
        <p className="text-xs text-slate-400">{item.label}</p>
        <p className="mt-2 text-2xl font-semibold text-white">{item.value}</p>
        <p className="mt-2 text-xs leading-5 text-slate-400">{item.detail}</p>
      </div>)}
    </div>

    <div className="mt-4 grid gap-3 lg:grid-cols-[1.15fr_.85fr]">
      <div className="rounded-xl border border-slate-700 bg-slate-950/35 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">Observed behavior</p>
        <div className="mt-3 space-y-2 text-sm text-slate-200">
          <p>• Native flow: {fundFlow ? `${eth(fundFlow.flow_summary?.observed_incoming_wei)} ETH in · ${eth(fundFlow.flow_summary?.observed_outgoing_wei)} ETH out` : 'unavailable'}.</p>
          <p>• Counterparties: {fundFlow?.top_counterparties?.length || report?.unique_counterparties || 0} observed in current evidence.</p>
          <p>• Review signals: {signals.length} deterministic signal{signals.length === 1 ? '' : 's'} from provider-indexed activity.</p>
          <p>• AI findings: {copilot?.claims?.length || 0} cited claim{copilot?.claims?.length === 1 ? '' : 's'} {copilot?.grounded ? 'passed grounding checks' : 'available in fallback/protected mode'}.</p>
        </div>
      </div>
      <div className="rounded-xl border border-amber-400/15 bg-amber-400/[0.035] p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-200">Confidence guardrail</p>
        <p className="mt-3 text-sm leading-6 text-slate-300">{coverage?.coverage_statement || report?.coverage || 'Evidence is bounded to retained native transactions and provider-indexed wallet history.'}</p>
        <p className="mt-3 text-xs leading-5 text-amber-100">No result should be treated as complete wallet history, beneficial ownership proof, or a fraud verdict.</p>
      </div>
    </div>

    <div className="mt-4 text-xs text-slate-500">Wallet: <span className="font-mono text-slate-300">{wallet}</span></div>
  </section>;
}

function TokenFlowPanel({ tokenFlow }) {
  if (!tokenFlow?.available) return null;
  const assets = tokenFlow.assets || [];
  return <section className="panel p-5" aria-labelledby="token-flow-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="eyebrow">Asset intelligence</p><h2 id="token-flow-title" className="mt-2 text-lg font-semibold text-white">ERC-20 / stablecoin movement</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Token activity is kept separate from native ETH paths so values are not incorrectly mixed or treated as conserved taint.</p></div>
      <span className="text-sm text-slate-300">{tokenFlow.records_examined || 0} records</span>
    </div>
    {assets.length ? <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-slate-950/70 text-xs text-slate-500"><tr><th className="px-4 py-3">Asset</th><th className="px-4 py-3">Incoming</th><th className="px-4 py-3">Outgoing</th><th className="px-4 py-3">Net observed</th><th className="px-4 py-3">Transfers</th><th className="px-4 py-3">Peers</th></tr></thead>
        <tbody>{assets.slice(0, 15).map((asset, index) => <tr key={`${asset.contract_address || asset.asset}-${index}`} className="border-t border-slate-800/80">
          <td className="px-4 py-3"><p className="font-semibold text-white">{asset.asset}</p>{asset.contract_address && <a href={`https://etherscan.io/token/${asset.contract_address}`} target="_blank" rel="noreferrer" className="mt-1 block font-mono text-xs text-cyan-300">{short(asset.contract_address)} ↗</a>}</td>
          <td className="px-4 py-3 text-emerald-300">{tokenAmount(asset.incoming_amount)}</td>
          <td className="px-4 py-3 text-amber-200">{tokenAmount(asset.outgoing_amount)}</td>
          <td className="px-4 py-3 text-slate-200">{tokenAmount(asset.net_amount)}</td>
          <td className="px-4 py-3 text-slate-300">{Number(asset.incoming_transfer_count || 0) + Number(asset.outgoing_transfer_count || 0)}</td>
          <td className="px-4 py-3 text-slate-300">{asset.unique_counterparties || 0}</td>
        </tr>)}</tbody>
      </table>
    </div> : <p className="mt-4 text-sm text-slate-400">No cached ERC-20 transfers were observed for this wallet.</p>}
    <p className="mt-4 text-xs leading-5 text-slate-500">{tokenFlow.scope}</p>
  </section>;
}

function PatternPanel({ motifs }) {
  if (!motifs) return null;
  const fanOut = motifs.fan_out || [];
  const fanIn = motifs.fan_in || [];
  const reciprocal = motifs.reciprocal_pairs || [];
  if (!fanOut.length && !fanIn.length && !reciprocal.length) return null;
  return <section className="panel p-5" aria-labelledby="patterns-title">
    <p className="eyebrow">Behavioral structure</p>
    <h2 id="patterns-title" className="mt-2 text-lg font-semibold text-white">Observed transaction patterns</h2>
    <div className="mt-4 grid gap-3 md:grid-cols-3">
      <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><p className="text-xs text-slate-500">Fan-out addresses</p><p className="mt-2 text-xl font-semibold text-white">{fanOut.length}</p><p className="mt-2 text-xs text-slate-400">Addresses with at least 3 observed outgoing edges.</p></div>
      <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><p className="text-xs text-slate-500">Fan-in addresses</p><p className="mt-2 text-xl font-semibold text-white">{fanIn.length}</p><p className="mt-2 text-xs text-slate-400">Addresses with at least 3 observed incoming edges.</p></div>
      <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><p className="text-xs text-slate-500">Reciprocal pairs</p><p className="mt-2 text-xl font-semibold text-white">{reciprocal.length}</p><p className="mt-2 text-xs text-slate-400">Observed pairs with transfers in both directions.</p></div>
    </div>
    <p className="mt-4 text-xs text-slate-500">{motifs.note}</p>
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

  const caseNote = useMemo(() => {
    if (!wallet) return '';
    const paths = fundFlow?.directed_paths || [];
    const highest = [...paths].sort((a, b) => Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0))[0];
    const parts = [
      'Added from unified Investigation workflow.',
      `Observed native flow: ${eth(fundFlow?.flow_summary?.observed_incoming_wei)} ETH in / ${eth(fundFlow?.flow_summary?.observed_outgoing_wei)} ETH out.`,
      `Observed counterparties: ${report?.unique_counterparties ?? fundFlow?.top_counterparties?.length ?? 0}.`,
      `ERC-20 assets observed: ${fundFlow?.token_flow?.assets?.length || 0}.`,
      `Entity path exposures: ${fundFlow?.entity_exposures?.length || 0}.`,
      `Grounded AI claims: ${copilot?.claims?.length || 0}.`,
    ];
    if (highest) parts.push(`Highest observed path risk score: ${highest.max_risk_score} across ${highest.hop_count} hop(s).`);
    parts.push('Coverage is bounded; this note is not a fraud verdict or ownership conclusion.');
    return parts.join(' ');
  }, [wallet, fundFlow, report, copilot]);

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid Ethereum address.'); return; }
    setLoading(true); setError(''); setFundFlow(null); setCopilot(null); setCoverage(null); setReport(null); setWallet(target.toLowerCase());
    const [flow, ai, coverageResult, reportResult] = await Promise.allSettled([
      api.getFundFlow(target), api.getCopilot(target), api.getWalletCoverageSummary(target), api.getWalletReport(target),
    ]);
    if (flow.status === 'fulfilled') setFundFlow(flow.value);
    if (ai.status === 'fulfilled') setCopilot(ai.value);
    if (coverageResult.status === 'fulfilled') setCoverage(coverageResult.value);
    if (reportResult.status === 'fulfilled') setReport(reportResult.value);
    const usefulLoaded = [flow, coverageResult, reportResult].some(item => item.status === 'fulfilled');
    if (!usefulLoaded) setError('Investigation services are currently unavailable. Try again shortly.');
    else if (flow.status === 'rejected') setError('Indexed evidence loaded, but fund-flow is temporarily unavailable.');
    else if (ai.status === 'rejected' && ai.reason?.status !== 401) setError('Evidence loaded. Grounded AI is temporarily unavailable.');
    setLoading(false);
  }

  function addToCase() {
    if (wallet) onSendToCase(wallet, caseNote);
  }

  return <div className="min-h-screen bg-[#0d1628] text-slate-100">
    <main className="platform-shell space-y-5 py-6">
      <section className="panel-strong p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow">Investigation</p><h1 className="mt-2 text-2xl font-semibold text-white">One wallet. One evidence trail.</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Run a single investigation that combines native ETH flow, ERC-20 activity, behavioral structure, coverage, cited AI findings, and case handoff.</p></div>
          <span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">Evidence-first</span>
        </div>
        <form onSubmit={investigate} className="mt-5 flex flex-col gap-3 sm:flex-row"><input value={address} onChange={e => setAddress(e.target.value)} className="soft-input min-w-0 flex-1 font-mono" placeholder="0x… Ethereum wallet address" aria-label="Ethereum wallet address" autoComplete="off" spellCheck="false" /><button className="primary-button sm:min-w-44" disabled={loading}>{loading ? 'Building intelligence…' : 'Investigate wallet'}</button></form>
        {error && <p role="alert" className="mt-3 text-sm text-amber-200">{error}</p>}
      </section>

      <WorkflowRail hasResult={Boolean(wallet)} onAddCase={addToCase} />

      {wallet && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Investigation summary">
        <div className="panel p-4 xl:col-span-1"><p className="eyebrow">Wallet</p><a href={`https://etherscan.io/address/${wallet}`} target="_blank" rel="noreferrer" className="mt-3 block break-all font-mono text-sm text-cyan-300">{short(wallet)} ↗</a></div>
        <div className="panel p-4"><p className="eyebrow">Native in</p><p className="mt-3 text-xl font-semibold text-emerald-300">{fundFlow ? eth(fundFlow.flow_summary?.observed_incoming_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Native out</p><p className="mt-3 text-xl font-semibold text-amber-200">{fundFlow ? eth(fundFlow.flow_summary?.observed_outgoing_wei) : '—'} ETH</p></div>
        <div className="panel p-4"><p className="eyebrow">Token assets</p><p className="mt-3 text-xl font-semibold text-violet-200">{fundFlow?.token_flow?.assets?.length ?? '—'}</p></div>
        <div className="panel p-4"><p className="eyebrow">Grounded findings</p><p className={`mt-3 text-xl font-semibold ${copilot?.grounded ? 'text-emerald-300' : 'text-slate-300'}`}>{copilot?.claims?.length ?? 0}</p></div>
      </section>}

      {wallet && <IntelligenceBrief wallet={wallet} fundFlow={fundFlow} report={report} coverage={coverage} copilot={copilot} />}

      {fundFlow && <TokenFlowPanel tokenFlow={fundFlow.token_flow} />}
      {fundFlow && <PatternPanel motifs={fundFlow.motifs} />}

      {fundFlow && <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]">
        <section className="panel p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Native fund-flow</p><h2 className="mt-2 text-lg font-semibold text-white">Observed directed paths</h2></div><span className="text-sm text-slate-300">{fundFlow.directed_paths?.length || 0} paths</span></div>
          <p className="mt-2 text-sm leading-6 text-amber-200">Path floor is the minimum observed ETH transfer on a path. It is not taint attribution.</p>
          <div className="mt-4 max-h-[620px] space-y-3 overflow-y-auto pr-1">{(fundFlow.directed_paths || []).slice(0, 50).map((path, index) => <div key={`${index}-${path.tx_hashes?.join('-')}`} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><div className="flex flex-wrap items-center gap-2"><span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{path.hop_count} hop{path.hop_count === 1 ? '' : 's'}</span><span className="text-sm text-slate-300">Path floor {eth(path.path_min_value_wei)} ETH</span><span className="text-sm text-slate-300">Max risk {path.max_risk_score}</span></div><div className="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-xs text-slate-300">{(path.addresses || []).map((item, i) => <span key={`${item}-${i}`} className="flex items-center gap-1.5"><a href={`https://etherscan.io/address/${item}`} target="_blank" rel="noreferrer" className="text-cyan-300">{short(item)}</a>{i < path.addresses.length - 1 && <span>→</span>}</span>)}</div><div className="mt-3 flex flex-wrap gap-2">{(path.tx_hashes || []).map(hash => <a key={hash} href={`https://etherscan.io/tx/${hash}`} target="_blank" rel="noreferrer" className="text-xs text-sky-300 underline">Verify {short(hash)} ↗</a>)}</div></div>)}</div>
        </section>

        <div className="space-y-5">
          <section className="panel p-5"><p className="eyebrow">Path attribution</p><h2 className="mt-2 text-lg font-semibold text-white">Source-labeled destinations</h2><div className="mt-4 space-y-3">{(fundFlow.entity_exposures || []).map((exposure, index) => <div key={`${exposure.destination}-${index}`} className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><a href={`https://etherscan.io/address/${exposure.destination}`} target="_blank" rel="noreferrer" className="break-all font-mono text-sm text-emerald-300">{short(exposure.destination)} ↗</a><p className="mt-1 text-sm text-slate-300">{exposure.hop_count} hops · path floor {eth(exposure.path_min_value_wei)} ETH</p>{(exposure.entity_labels || []).map((label, i) => <p key={i} className="mt-2 text-sm text-white">{label.entity_name || label.entity_id} <span className="text-slate-300">· {label.source}</span></p>)}</div>)}{!fundFlow.entity_exposures?.length && <p className="text-sm text-slate-400">No source-labeled destination was reached in the bounded native path set.</p>}</div></section>
          <section className="panel p-5"><p className="eyebrow">Counterparty concentration</p><h2 className="mt-2 text-lg font-semibold text-white">Top observed peers</h2><div className="mt-4 space-y-3">{(fundFlow.top_counterparties || []).slice(0, 10).map(row => <div key={row.address} className="flex flex-col gap-1 border-b border-slate-700/70 pb-3 text-sm sm:flex-row sm:items-center sm:justify-between"><a href={`https://etherscan.io/address/${row.address}`} target="_blank" rel="noreferrer" className="font-mono text-cyan-300">{short(row.address)}</a><span className="text-slate-300">{row.tx_count} tx · {eth(row.total_wei)} ETH</span></div>)}</div></section>
        </div>
      </div>}

      {report?.behavioral_signals?.length > 0 && <section className="panel p-5">
        <p className="eyebrow">Deterministic review signals</p><h2 className="mt-2 text-lg font-semibold text-white">Behavior requiring analyst attention</h2>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">{report.behavioral_signals.map((signal, index) => <article key={`${signal.code}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><div className="flex items-start justify-between gap-3"><p className="font-medium text-white">{signal.title || signal.code}</p><span className="text-xs text-slate-500">{signal.observed_count ?? '—'} records</span></div><p className="mt-2 text-sm leading-6 text-slate-400">{signal.explanation}</p><div className="mt-3 flex flex-wrap gap-2">{(signal.evidence || []).slice(0, 5).map(item => <a key={item.tx_hash} href={item.url || `https://etherscan.io/tx/${item.tx_hash}`} target="_blank" rel="noreferrer" className="text-xs text-cyan-300 underline">Evidence {short(item.tx_hash)} ↗</a>)}</div></article>)}</div>
      </section>}

      {copilot && <section className="panel-strong p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Grounded AI findings</p><h2 className="mt-2 text-lg font-semibold text-white">Claims tied to evidence</h2></div><div className="flex flex-wrap gap-2"><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-200">{copilot.mode || 'deterministic'}</span><span className={`status-pill ${copilot.grounded ? 'border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200' : 'border-amber-400/20 bg-amber-400/[0.06] text-amber-200'}`}>{copilot.grounded ? 'grounded' : 'fallback'}</span></div></div>
        <p className="mt-2 text-sm text-slate-300">Records examined: {copilot.coverage?.records_examined ?? 0}. Every displayed claim should remain independently verifiable.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">{(copilot.claims || []).map((claim, index) => <article key={index} className="rounded-xl border border-slate-700 bg-slate-950/35 p-4"><p className="text-sm leading-6 text-slate-100">{claim.text}</p><div className="mt-3 flex flex-wrap gap-2">{(claim.finding_ids || []).map(id => <span key={id} className="rounded border border-violet-400/20 bg-violet-400/[0.05] px-2 py-1 font-mono text-xs text-violet-200">{id}</span>)}</div>{(claim.citations || []).flatMap(citation => citation.evidence_urls || []).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="mt-2 mr-3 inline-block text-xs text-sky-300 underline">Verify transaction ↗</a>)}</article>)}</div>
        {copilot.uncertainty && <p className="mt-5 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-4 py-3 text-sm leading-6 text-amber-100">Uncertainty: {copilot.uncertainty}</p>}
      </section>}

      {wallet && <section className="panel-strong flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="eyebrow text-cyan-300">Preserve the investigation</p><h2 className="mt-2 text-lg font-semibold text-white">Move evidence into a case</h2><p className="mt-2 max-w-2xl text-sm text-slate-300">The wallet is transferred with a concise evidence summary so an analyst can continue without rebuilding context.</p></div><button type="button" onClick={addToCase} className="primary-button whitespace-nowrap">Add investigation to case</button></section>}
    </main>
  </div>;
}

export default function AppV3() {
  const [workspace, setWorkspace] = useState('lab');
  const [caseEvidence, setCaseEvidence] = useState(null);
  function sendWalletToCase(address, note = 'Added from Investigation workflow.') {
    setCaseEvidence({ item_type: 'address', item_key: address, note });
    setWorkspace('cases');
  }
  return <div className="min-h-screen bg-[#0d1628]">
    <div className="sticky top-0 z-[80] border-b border-slate-800 bg-[#09111f]/95 px-3 py-2 backdrop-blur">
      <div className="mx-auto flex max-w-[1540px] flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><span className="text-sm font-semibold tracking-[0.15em] text-cyan-300">CHAINSCOPE</span><span className="hidden text-xs text-slate-400 sm:inline">Investigation OS</span></div>
        <nav className="flex max-w-full gap-1 overflow-x-auto" aria-label="Product workspace"><button onClick={() => setWorkspace('lab')} aria-current={workspace === 'lab' ? 'page' : undefined} className={`workspace-chip ${workspace === 'lab' ? 'workspace-chip-active' : ''}`}>Investigate</button><button onClick={() => setWorkspace('platform')} aria-current={workspace === 'platform' ? 'page' : undefined} className={`workspace-chip ${workspace === 'platform' ? 'workspace-chip-active' : ''}`}>Monitor</button><button onClick={() => setWorkspace('cases')} aria-current={workspace === 'cases' ? 'page' : undefined} className={`workspace-chip ${workspace === 'cases' ? 'workspace-chip-active' : ''}`}>Cases</button></nav>
      </div>
    </div>
    {workspace === 'platform' && <App />}
    {workspace === 'lab' && <InvestigationLab onSendToCase={sendWalletToCase} />}
    {workspace === 'cases' && <div className="min-h-screen bg-[#0d1628] text-slate-100"><main className="platform-shell py-6"><CaseWorkspace initialEvidence={caseEvidence} onEvidenceConsumed={() => setCaseEvidence(null)} /></main></div>}
  </div>;
}
