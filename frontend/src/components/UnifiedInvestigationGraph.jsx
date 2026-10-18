import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

const BubbleInvestigationGraph = lazy(() => import('./ScalableBubbleInvestigationGraph'));
const normalized = value => String(value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 8)}…${value.slice(-5)}` : '—';
const edgeKey = edge => [edge.tx_hash, normalized(edge.source), normalized(edge.target), edge.asset, edge.category, edge.value].join('|');

function ethFromWei(value) {
  try {
    return (Number(BigInt(String(value || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 });
  } catch {
    return '—';
  }
}

function numberText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value ?? '—');
}

function mergeGraph(previous, incoming) {
  if (!previous) return incoming;
  const seenEdges = new Set((previous.edges || []).map(edgeKey));
  const freshEdges = (incoming.edges || []).filter(edge => {
    const key = edgeKey(edge);
    if (seenEdges.has(key)) return false;
    seenEdges.add(key);
    return true;
  });
  const nodeMap = new Map((previous.nodes || []).map(node => [normalized(node.id), node]));
  (incoming.nodes || []).forEach(node => {
    const id = normalized(node.id);
    if (!id) return;
    const old = nodeMap.get(id) || {};
    nodeMap.set(id, {
      ...old,
      ...node,
      verified_entities: node.verified_entities?.length ? node.verified_entities : old.verified_entities,
      max_observed_risk_score: Math.max(Number(old.max_observed_risk_score || 0), Number(node.max_observed_risk_score || 0)),
    });
  });
  return { ...previous, edges: [...(previous.edges || []), ...freshEdges], nodes: [...nodeMap.values()] };
}

function MultiHopTracePanel({ wallet, fundFlow }) {
  const [hopFilter, setHopFilter] = useState('all');
  const paths = useMemo(() => {
    const source = Array.isArray(fundFlow?.directed_paths) ? fundFlow.directed_paths : [];
    return [...source]
      .filter(path => hopFilter === 'all' || Number(path.hop_count) === Number(hopFilter))
      .sort((a, b) => {
        const risk = Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0);
        if (risk !== 0) return risk;
        return Number(b.hop_count || 0) - Number(a.hop_count || 0);
      })
      .slice(0, 10);
  }, [fundFlow, hopFilter]);

  const exposures = useMemo(() => new Map(
    (fundFlow?.entity_exposures || []).map(item => [normalized(item.destination), item]),
  ), [fundFlow]);

  if (!fundFlow?.directed_paths?.length) return null;

  return <section className="panel p-5" aria-labelledby="multi-hop-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow">Multi-hop tracing</p>
        <h2 id="multi-hop-title" className="mt-2 text-lg font-semibold text-white">Where observed ETH moved next</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Ranked directed paths from the investigated wallet across up to three retained-data hops. Path floor is the smallest observed ETH transfer on the path, not taint attribution.</p>
      </div>
      <div className="flex overflow-hidden rounded-lg border border-slate-700 text-xs">
        {['all', '1', '2', '3'].map(value => <button
          key={value}
          type="button"
          onClick={() => setHopFilter(value)}
          className={`px-3 py-2 ${hopFilter === value ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800'}`}
        >{value === 'all' ? 'All paths' : `${value} hop${value === '1' ? '' : 's'}`}</button>)}
      </div>
    </div>

    <div className="mt-4 grid gap-3 xl:grid-cols-2">
      {paths.map((path, index) => {
        const destination = path.addresses?.[path.addresses.length - 1];
        const exposure = exposures.get(normalized(destination));
        return <article key={`${path.tx_hashes?.join('-')}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <span className="status-pill border-violet-400/20 bg-violet-400/[0.05] text-violet-200">{path.hop_count} hop{path.hop_count === 1 ? '' : 's'}</span>
              <span className={`status-pill ${Number(path.max_risk_score || 0) >= 70 ? 'border-rose-400/20 bg-rose-400/[0.06] text-rose-200' : 'border-slate-700 bg-slate-950/50 text-slate-300'}`}>max risk {path.max_risk_score ?? 0}</span>
              {exposure && <span className="status-pill border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200">labeled destination</span>}
            </div>
            <span className="text-xs text-slate-400">floor {ethFromWei(path.path_min_value_wei)} ETH</span>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-1.5 font-mono text-xs text-slate-300">
            {(path.addresses || []).map((address, addressIndex) => <span key={`${address}-${addressIndex}`} className="flex items-center gap-1.5">
              <a href={`https://etherscan.io/address/${address}`} target="_blank" rel="noreferrer" className={normalized(address) === normalized(wallet) ? 'text-cyan-300' : 'text-slate-300 hover:text-cyan-200'}>{short(address)}</a>
              {addressIndex < path.addresses.length - 1 && <span className="text-slate-600">→</span>}
            </span>)}
          </div>

          {exposure && <div className="mt-3 rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] px-3 py-2 text-xs text-slate-300">
            {(exposure.entity_labels || []).slice(0, 2).map((label, labelIndex) => <p key={`${label.entity_id || label.entity_name}-${labelIndex}`}><span className="font-medium text-emerald-200">{label.entity_name || label.entity_id}</span>{label.source ? ` · ${label.source}` : ''}</p>)}
          </div>}

          <div className="mt-3 flex flex-wrap gap-3">
            {(path.tx_hashes || []).map((hash, txIndex) => <a key={`${hash}-${txIndex}`} href={`https://etherscan.io/tx/${hash}`} target="_blank" rel="noreferrer" className="text-xs text-sky-300 underline">Hop {txIndex + 1} evidence ↗</a>)}
          </div>
        </article>;
      })}
    </div>
    {!paths.length && <p className="mt-4 text-sm text-slate-400">No paths match this hop filter.</p>}
  </section>;
}

function TokenFlowExplorer({ tokenFlow }) {
  const assets = tokenFlow?.assets || [];
  const [selectedAsset, setSelectedAsset] = useState('ALL');
  const edges = useMemo(() => {
    const source = tokenFlow?.edges || [];
    return source
      .filter(edge => selectedAsset === 'ALL' || String(edge.asset || '').toUpperCase() === selectedAsset)
      .slice(0, 18);
  }, [tokenFlow, selectedAsset]);

  useEffect(() => {
    if (selectedAsset !== 'ALL' && !assets.some(asset => String(asset.asset || '').toUpperCase() === selectedAsset)) setSelectedAsset('ALL');
  }, [assets, selectedAsset]);

  if (!tokenFlow?.available || !assets.length) return null;

  return <section className="panel p-5" aria-labelledby="token-explorer-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow">Token-flow intelligence</p>
        <h2 id="token-explorer-title" className="mt-2 text-lg font-semibold text-white">ERC-20 movement by asset</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Inspect provider-indexed token transfers without mixing unlike token units or claiming multi-hop conservation through swaps and contracts.</p>
      </div>
      <select value={selectedAsset} onChange={event => setSelectedAsset(event.target.value)} className="soft-input min-w-44" aria-label="Token-flow asset">
        <option value="ALL">All token assets</option>
        {assets.slice(0, 30).map(asset => <option key={`${asset.contract_address || ''}-${asset.asset}`} value={String(asset.asset || '').toUpperCase()}>{asset.asset}</option>)}
      </select>
    </div>

    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {assets.slice(0, 4).map(asset => <button key={`${asset.contract_address || ''}-${asset.asset}`} type="button" onClick={() => setSelectedAsset(String(asset.asset || '').toUpperCase())} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4 text-left hover:border-violet-400/30">
        <div className="flex items-start justify-between gap-2"><p className="font-semibold text-white">{asset.asset}</p><span className="text-[10px] text-slate-500">{Number(asset.incoming_transfer_count || 0) + Number(asset.outgoing_transfer_count || 0)} tx</span></div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><p className="text-slate-500">In</p><p className="mt-1 text-emerald-300">{numberText(asset.incoming_amount)}</p></div><div><p className="text-slate-500">Out</p><p className="mt-1 text-amber-200">{numberText(asset.outgoing_amount)}</p></div></div>
        <p className="mt-3 text-xs text-slate-500">{asset.unique_counterparties || 0} peers · net {numberText(asset.net_amount)}</p>
      </button>)}
    </div>

    <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800" role="region" tabIndex={0} aria-label="Token transfer evidence">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="bg-slate-950/70 text-xs text-slate-500"><tr><th className="px-4 py-3">Direction</th><th className="px-4 py-3">Asset</th><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Amount</th><th className="px-4 py-3">Evidence</th></tr></thead>
        <tbody>{edges.map((edge, index) => <tr key={`${edge.tx_hash}-${edge.contract_address || ''}-${index}`} className="border-t border-slate-800/80">
          <td className="px-4 py-3"><span className={`status-pill ${edge.direction_from_root === 'incoming' ? 'border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-200' : 'border-amber-400/20 bg-amber-400/[0.05] text-amber-200'}`}>{edge.direction_from_root || 'observed'}</span></td>
          <td className="px-4 py-3 font-medium text-white">{edge.asset || 'TOKEN'}</td>
          <td className="px-4 py-3 font-mono text-xs text-slate-300">{short(edge.source)}</td>
          <td className="px-4 py-3 font-mono text-xs text-slate-300">{short(edge.target)}</td>
          <td className="px-4 py-3 text-slate-200">{numberText(edge.value)}</td>
          <td className="px-4 py-3">{edge.evidence_url ? <a href={edge.evidence_url} target="_blank" rel="noreferrer" className="text-cyan-300 underline">Verify tx ↗</a> : '—'}</td>
        </tr>)}</tbody>
      </table>
      {!edges.length && <p className="p-6 text-sm text-slate-400">No token transfers match this asset.</p>}
    </div>
    <p className="mt-3 text-xs leading-5 text-slate-500">{tokenFlow.scope}</p>
  </section>;
}

function ExplainableFindings({ fundFlow }) {
  const findings = useMemo(() => {
    if (!fundFlow) return [];
    const results = [];
    const paths = fundFlow.directed_paths || [];
    const highest = [...paths].sort((a, b) => Number(b.max_risk_score || 0) - Number(a.max_risk_score || 0))[0];
    const motifs = fundFlow.motifs || {};
    const fanOut = (motifs.fan_out || [])[0];
    const fanIn = (motifs.fan_in || [])[0];
    const reciprocal = motifs.reciprocal_pairs || [];
    const exposures = fundFlow.entity_exposures || [];
    const assets = fundFlow.token_flow?.assets || [];
    const topAsset = [...assets].sort((a, b) => (Number(b.incoming_transfer_count || 0) + Number(b.outgoing_transfer_count || 0)) - (Number(a.incoming_transfer_count || 0) + Number(a.outgoing_transfer_count || 0)))[0];
    const incoming = Number(fundFlow.flow_summary?.observed_incoming_wei || 0);
    const outgoing = Number(fundFlow.flow_summary?.observed_outgoing_wei || 0);

    if (highest) results.push({
      code: 'PATH_RISK',
      title: 'Highest-risk observed native path',
      level: Number(highest.max_risk_score || 0) >= 70 ? 'high' : Number(highest.max_risk_score || 0) >= 30 ? 'medium' : 'info',
      explanation: `A ${highest.hop_count}-hop retained-data path reaches a maximum connected risk score of ${highest.max_risk_score ?? 0}. The path floor is ${ethFromWei(highest.path_min_value_wei)} ETH.`,
      evidence: (highest.tx_hashes || []).map(hash => ({ label: short(hash), url: `https://etherscan.io/tx/${hash}` })),
      guardrail: 'This score describes observed connected evidence; it does not prove taint, intent, or common ownership.',
    });

    if (fanOut) results.push({
      code: 'FAN_OUT',
      title: 'Fund dispersion pattern',
      level: fanOut.edge_count >= 8 ? 'medium' : 'info',
      explanation: `${short(fanOut.address)} has ${fanOut.edge_count} observed outgoing native edges in the retained graph.`,
      evidence: [],
      guardrail: 'Fan-out is a structural pattern and can occur in legitimate operational activity.',
    });

    if (fanIn) results.push({
      code: 'FAN_IN',
      title: 'Fund consolidation pattern',
      level: fanIn.edge_count >= 8 ? 'medium' : 'info',
      explanation: `${short(fanIn.address)} has ${fanIn.edge_count} observed incoming native edges in the retained graph.`,
      evidence: [],
      guardrail: 'Fan-in alone does not establish coordinated ownership or suspicious activity.',
    });

    if (reciprocal.length) results.push({
      code: 'RECIPROCAL',
      title: 'Bidirectional relationships observed',
      level: reciprocal.length >= 4 ? 'medium' : 'info',
      explanation: `${reciprocal.length} address pair${reciprocal.length === 1 ? '' : 's'} transferred value in both directions within the retained evidence.`,
      evidence: [],
      guardrail: 'Reciprocal transfers are a review lead, not proof of circular laundering or common control.',
    });

    if (exposures.length) results.push({
      code: 'ENTITY_EXPOSURE',
      title: 'Source-labeled destination reached',
      level: 'medium',
      explanation: `${exposures.length} bounded native path${exposures.length === 1 ? '' : 's'} reach an address with source-attributed entity context.`,
      evidence: exposures.slice(0, 3).flatMap(exposure => (exposure.evidence_urls || []).slice(0, 2).map(url => ({ label: short(exposure.destination), url }))),
      guardrail: 'Exposure means a path reaches a labeled address; it does not prove the root controls or belongs to that entity.',
    });

    if (topAsset) results.push({
      code: 'TOKEN_ACTIVITY',
      title: 'Most active indexed token',
      level: 'info',
      explanation: `${topAsset.asset} has ${Number(topAsset.incoming_transfer_count || 0) + Number(topAsset.outgoing_transfer_count || 0)} indexed transfers across ${topAsset.unique_counterparties || 0} counterparties in the token evidence cache.`,
      evidence: [],
      guardrail: 'Token amounts remain asset-specific and are not converted into a common value metric here.',
    });

    if (incoming > 0 || outgoing > 0) {
      const larger = Math.max(incoming, outgoing), smaller = Math.max(1, Math.min(incoming, outgoing));
      const ratio = larger / smaller;
      if (ratio >= 3) results.push({
        code: 'FLOW_IMBALANCE',
        title: 'Large observed native-flow imbalance',
        level: 'info',
        explanation: `Observed retained native flow is materially asymmetric: ${ethFromWei(String(incoming))} ETH incoming versus ${ethFromWei(String(outgoing))} ETH outgoing.`,
        evidence: [],
        guardrail: 'This comparison is limited to retained evidence and is not a current wallet balance calculation.',
      });
    }

    return results.slice(0, 6);
  }, [fundFlow]);

  if (!findings.length) return null;

  const styles = {
    high: 'border-rose-400/20 bg-rose-400/[0.045] text-rose-200',
    medium: 'border-amber-400/20 bg-amber-400/[0.045] text-amber-200',
    info: 'border-cyan-400/15 bg-cyan-400/[0.035] text-cyan-200',
  };

  return <section className="panel-strong p-5 sm:p-6" aria-labelledby="explainable-findings-title">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow text-cyan-300">Explainable intelligence</p>
        <h2 id="explainable-findings-title" className="mt-2 text-lg font-semibold text-white">Why this wallet deserves review</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">Deterministic leads derived from loaded evidence with an explicit reason and limitation for every finding.</p>
      </div>
      <span className="status-pill border-slate-700 bg-slate-950/60 text-slate-300">{findings.length} explainable leads</span>
    </div>
    <div className="mt-5 grid gap-3 lg:grid-cols-2">
      {findings.map(finding => <article key={finding.code} className={`rounded-xl border p-4 ${styles[finding.level] || styles.info}`}>
        <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] opacity-75">{finding.code.replaceAll('_', ' ')}</p><h3 className="mt-1 font-semibold text-white">{finding.title}</h3></div><span className="rounded-full border border-current/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em]">{finding.level}</span></div>
        <p className="mt-3 text-sm leading-6 text-slate-200">{finding.explanation}</p>
        {finding.evidence.length > 0 && <div className="mt-3 flex flex-wrap gap-3">{finding.evidence.map((item, index) => <a key={`${item.url}-${index}`} href={item.url} target="_blank" rel="noreferrer" className="text-xs text-sky-300 underline">Evidence {item.label} ↗</a>)}</div>}
        <p className="mt-3 border-t border-white/[0.06] pt-3 text-xs leading-5 text-slate-500">{finding.guardrail}</p>
      </article>)}
    </div>
  </section>;
}

export default function UnifiedInvestigationGraph({ wallet, fundFlow }) {
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandingAddress, setExpandingAddress] = useState('');
  const [expandedAddresses, setExpandedAddresses] = useState([]);

  useEffect(() => {
    let cancelled = false;
    if (!wallet) { setGraph(null); return undefined; }
    setLoading(true);
    setError('');
    setExpandedAddresses([]);
    api.getWalletGraph(wallet)
      .then(result => { if (!cancelled) setGraph(result); })
      .catch(failure => { if (!cancelled) setError(failure.message || 'Interactive graph evidence is unavailable.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [wallet]);

  const transactions = useMemo(() => {
    const records = [];
    const seen = new Set();
    const append = tx => {
      const key = [tx.hash, normalized(tx.from_address), normalized(tx.to_address), tx.asset, tx.category, tx.value].join('|');
      if (!tx.hash || !tx.from_address || !tx.to_address || seen.has(key)) return;
      seen.add(key);
      records.push(tx);
    };
    (graph?.edges || []).forEach(edge => append({
      hash: edge.tx_hash,
      from_address: edge.source,
      to_address: edge.target,
      value: edge.value ?? edge.value_wei,
      asset: edge.asset || 'ETH',
      category: edge.category || 'external',
      risk_score: edge.risk_score,
      block_number: edge.block_number,
      timestamp: edge.block_timestamp || edge.timestamp,
      evidence_url: edge.evidence_url,
    }));
    (fundFlow?.token_flow?.edges || []).forEach(edge => append({
      hash: edge.tx_hash,
      from_address: edge.source,
      to_address: edge.target,
      value: edge.value,
      asset: edge.asset,
      category: 'erc20',
      risk_score: edge.risk_score,
      block_number: edge.block_number,
      timestamp: edge.block_timestamp,
      evidence_url: edge.evidence_url,
    }));
    return records;
  }, [graph, fundFlow]);

  const nodeContext = useMemo(() => {
    const context = {};
    (graph?.nodes || []).forEach(node => {
      context[normalized(node.id)] = {
        maxRisk: node.max_observed_risk_score,
        entityLabels: node.verified_entities || [],
      };
    });
    (fundFlow?.entity_exposures || []).forEach(exposure => {
      const id = normalized(exposure.destination);
      context[id] = {
        ...(context[id] || {}),
        entityLabels: exposure.entity_labels || context[id]?.entityLabels || [],
      };
    });
    return context;
  }, [graph, fundFlow]);

  async function expandAddress(address) {
    const target = normalized(address);
    if (!target || target === normalized(wallet) || expandedAddresses.includes(target) || expandingAddress) return;
    if (expandedAddresses.length >= 5) {
      setError('Expansion limit reached: maximum five counterparties per investigation.');
      return;
    }
    setExpandingAddress(target);
    setError('');
    try {
      const result = await api.getWalletGraph(target);
      setGraph(previous => mergeGraph(previous, result));
      setExpandedAddresses(previous => [...previous, target]);
    } catch (failure) {
      setError(failure.message || 'Unable to expand this observed wallet.');
    } finally {
      setExpandingAddress('');
    }
  }

  return <section className="space-y-5" aria-labelledby="unified-graph-title">
    <ExplainableFindings fundFlow={fundFlow} />
    <MultiHopTracePanel wallet={wallet} fundFlow={fundFlow} />
    <TokenFlowExplorer tokenFlow={fundFlow?.token_flow} />

    <div className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Graph investigation</p>
          <h2 id="unified-graph-title" className="mt-2 text-lg font-semibold text-white">Follow the evidence visually</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">The bubble map combines indexed wallet evidence with separately scoped token edges. Expand an observed counterparty without losing the investigation context.</p>
        </div>
        <span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{expandedAddresses.length}/5 expansions</span>
      </div>
      {loading && <p role="status" className="mt-4 text-sm text-slate-300">Loading indexed graph evidence…</p>}
      {error && <p role="alert" className="mt-4 text-sm text-amber-200">{error}</p>}
    </div>

    {!loading && transactions.length > 0 && <Suspense fallback={<div className="panel p-6 text-sm text-slate-300" role="status">Loading 3D bubble investigation map…</div>}>
      <BubbleInvestigationGraph
        transactions={transactions}
        rootAddress={wallet}
        onExpandAddress={expandAddress}
        expandingAddress={expandingAddress}
        expandedAddresses={expandedAddresses}
        nodeContext={nodeContext}
      />
    </Suspense>}
    {!loading && !transactions.length && !error && <div className="panel p-6 text-sm text-slate-400">No graphable indexed transfers are currently available for this wallet.</div>}
  </section>;
}
