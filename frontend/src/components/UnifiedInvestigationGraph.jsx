import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import InvestigationGraph from './InvestigationGraph';

const normalized = value => String(value || '').toLowerCase();
const edgeKey = edge => [edge.tx_hash, normalized(edge.source), normalized(edge.target), edge.asset, edge.category, edge.value].join('|');

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
      value: edge.value,
      asset: edge.asset || (edge.category === 'external' ? 'ETH' : undefined),
      category: edge.category || 'external',
      risk_score: edge.risk_score,
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

  return <section className="space-y-3" aria-labelledby="unified-graph-title">
    <div className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Graph investigation</p>
          <h2 id="unified-graph-title" className="mt-2 text-lg font-semibold text-white">Follow the evidence visually</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Inspect loaded wallet relationships, select a counterparty, expand one bounded hop, and verify each connection without leaving the investigation.</p>
        </div>
        <span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{expandedAddresses.length}/5 expansions</span>
      </div>
      {loading && <p role="status" className="mt-4 text-sm text-slate-300">Loading indexed graph evidence…</p>}
      {error && <p role="alert" className="mt-4 text-sm text-amber-200">{error}</p>}
    </div>
    {!loading && transactions.length > 0 && <InvestigationGraph
      transactions={transactions}
      rootAddress={wallet}
      onExpandAddress={expandAddress}
      expandingAddress={expandingAddress}
      expandedAddresses={expandedAddresses}
      nodeContext={nodeContext}
    />}
    {!loading && !transactions.length && !error && <div className="panel p-6 text-sm text-slate-400">No graphable indexed transfers are currently available for this wallet.</div>}
  </section>;
}
