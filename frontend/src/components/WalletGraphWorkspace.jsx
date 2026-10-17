import { useMemo, useState } from 'react';
import { api } from '../api/client';
import ScalableBubbleInvestigationGraph from './ScalableBubbleInvestigationGraph';

const VALID = /^0x[a-fA-F0-9]{40}$/;

function graphError(failure, fallback) {
  if (failure?.status === 429) {
    const wait = Number(failure.retryAfter || 0);
    return wait > 0
      ? `Graph request limit reached. Retry in about ${wait} second${wait === 1 ? '' : 's'}.`
      : 'Graph request limit reached. Retry shortly.';
  }
  if (failure?.status === 503) return 'Investigation capacity is busy. Retry in a few seconds.';
  return failure?.message || fallback;
}

export default function WalletGraphWorkspace({ flagged = [], onSelect }) {
  void flagged;
  void onSelect;
  const [address, setAddress] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadedPages, setLoadedPages] = useState(1);
  const [expansions, setExpansions] = useState({});
  const [expanding, setExpanding] = useState('');

  async function investigate(event) {
    event.preventDefault();
    const wallet = address.trim();
    if (!VALID.test(wallet)) {
      setError('Enter a valid Ethereum wallet address.');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);
    setLoadedPages(1);
    setExpansions({});
    try {
      const response = await api.getWalletGraph(wallet);
      setResult(response);
    } catch (failure) {
      setResult(null);
      setError(graphError(failure, 'Unable to retrieve wallet graph.'));
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (!result || loadingMore) return;
    const next = result.next_page_keys || {};
    if (!next.outgoing && !next.incoming) return;
    setLoadingMore(true);
    setError('');
    try {
      const page = await api.getWalletTransfers(result.root, {
        outgoing_page_key: next.outgoing,
        incoming_page_key: next.incoming,
      }, { outgoing: Boolean(next.outgoing), incoming: Boolean(next.incoming) });
      const added = (page.transfers || []).filter(tx => tx.hash && tx.from_address && tx.to_address).map(tx => ({
        source: tx.from_address,
        target: tx.to_address,
        tx_hash: tx.hash,
        value: tx.value,
        asset: tx.asset,
        category: tx.category,
        block_number_hex: tx.block_number_hex,
        evidence_url: tx.evidence_url,
      }));
      setResult(previous => {
        const seen = new Set((previous.edges || []).map(edge => [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|')));
        const fresh = added.filter(edge => {
          const key = [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        return {
          ...previous,
          edges: [...(previous.edges || []), ...fresh],
          next_page_keys: { outgoing: page.outgoing_next_page_key, incoming: page.incoming_next_page_key },
        };
      });
      setLoadedPages(count => count + 1);
    } catch (failure) {
      setError(graphError(failure, 'Unable to load older transfers.'));
    } finally {
      setLoadingMore(false);
    }
  }

  async function expandWallet(walletInput) {
    const wallet = String(walletInput || '').trim().toLowerCase();
    if (!result || !VALID.test(wallet)) { setError('Choose a valid observed counterparty address.'); return; }
    const known = new Set((result.edges || []).flatMap(edge => [edge.source?.toLowerCase(), edge.target?.toLowerCase()]));
    if (!known.has(wallet)) { setError('Only an address already observed in this graph can be expanded.'); return; }
    if (wallet === result.root?.toLowerCase()) { setError('The root wallet is already loaded.'); return; }
    if (expansions[wallet]) { setError('This wallet has already been expanded.'); return; }
    if (Object.keys(expansions).length >= 5) { setError('Expansion limit reached: five counterparties per investigation.'); return; }
    setExpanding(wallet);
    setError('');
    try {
      const page = await api.getWalletGraph(wallet);
      setResult(previous => {
        const seen = new Set((previous.edges || []).map(edge => [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|')));
        const fresh = (page.edges || []).filter(edge => {
          const key = [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        const previousNodes = previous.nodes || [];
        const nodeIds = new Set(previousNodes.map(node => node.id?.toLowerCase()));
        const newNodes = (page.nodes || []).filter(node => node.id && !nodeIds.has(node.id.toLowerCase()));
        return { ...previous, edges: [...(previous.edges || []), ...fresh], nodes: [...previousNodes, ...newNodes] };
      });
      setExpansions(previous => ({ ...previous, [wallet]: {
        edges: (page.edges || []).length,
        moreOutgoing: Boolean(page.next_page_keys?.outgoing),
        moreIncoming: Boolean(page.next_page_keys?.incoming),
        verifiedEntityMatches: Number(page.verified_entity_matches || 0),
      } }));
    } catch (failure) {
      setError(graphError(failure, 'Counterparty expansion failed.'));
    } finally {
      setExpanding('');
    }
  }

  const records = result ? (result.edges || []).filter(edge => edge.source && edge.target && edge.tx_hash).map(edge => ({
    hash: edge.tx_hash,
    from_address: edge.source,
    to_address: edge.target,
    value: edge.value ?? edge.value_wei,
    asset: edge.asset || 'ETH',
    category: edge.category || 'external',
    block_number_hex: edge.block_number_hex,
    timestamp: edge.block_timestamp || edge.timestamp,
    evidence_url: edge.evidence_url,
    risk_score: edge.risk_score ?? null,
  })) : [];

  const nodeContext = useMemo(() => {
    const context = {};
    (result?.nodes || []).forEach(node => {
      if (!node.id) return;
      context[node.id.toLowerCase()] = {
        maxRisk: node.max_observed_risk_score ?? null,
        entityLabels: Array.isArray(node.verified_entities) ? node.verified_entities : [],
      };
    });
    return context;
  }, [result]);

  const verifiedNodes = result ? (result.nodes || []).filter(node => Array.isArray(node.verified_entities) && node.verified_entities.length > 0) : [];
  const expansionCount = Object.keys(expansions).length;
  const observedWallets = result ? [...new Set((result.edges || []).flatMap(edge => [edge.source?.toLowerCase(), edge.target?.toLowerCase()]))].filter(Boolean) : [];

  return <div className="space-y-5">
    <form onSubmit={investigate} className="panel-strong relative overflow-hidden p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-violet-400/[0.055] blur-3xl" />
      <div className="relative">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Evidence network</p>
            <h2 className="mt-2 text-xl font-semibold text-white">Explore an Ethereum wallet graph</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Build a bounded evidence graph, inspect a wallet by clicking it, expand observed counterparties one hop, and verify every loaded transfer independently.</p>
          </div>
          <span className="status-pill border-violet-400/20 bg-violet-400/[0.07] text-violet-300">Interactive evidence</span>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input aria-label="Ethereum wallet for graph" value={address} onChange={event => setAddress(event.target.value)} placeholder="0x… Ethereum wallet address" className="soft-input min-w-0 flex-1 font-mono" />
          <button disabled={loading} className="primary-button min-w-36">{loading ? 'Building…' : 'Build graph'}</button>
          {result && <button type="button" onClick={() => { setResult(null); setError(''); setExpansions({}); }} className="secondary-button">Clear</button>}
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
      </div>
    </form>

    {result && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="panel p-4"><p className="eyebrow">Observed edges</p><p className="mt-3 text-2xl font-semibold text-white">{records.length}</p><p className="mt-2 text-xs text-slate-500">Evidence-linked transfers</p></div>
        <div className="panel p-4"><p className="eyebrow">Observed wallets</p><p className="mt-3 text-2xl font-semibold text-cyan-300">{observedWallets.length}</p><p className="mt-2 text-xs text-slate-500">Loaded graph only</p></div>
        <div className="panel p-4"><p className="eyebrow">Verified entity matches</p><p className={`mt-3 text-2xl font-semibold ${verifiedNodes.length ? 'text-emerald-300' : 'text-slate-500'}`}>{verifiedNodes.length}</p><p className="mt-2 text-xs text-slate-500">Source-attributed exact matches</p></div>
        <div className="panel p-4"><p className="eyebrow">Expanded wallets</p><p className="mt-3 text-2xl font-semibold text-violet-300">{expansionCount}/5</p><p className="mt-2 text-xs text-slate-500">One-hop context merged</p></div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div><p className="eyebrow">Root address</p><a href={`https://etherscan.io/address/${result.root}`} target="_blank" rel="noopener noreferrer" className="mt-2 block break-all font-mono text-sm text-cyan-300">{result.root} ↗</a><p className="mt-2 text-xs leading-5 text-amber-300">{result.scope || 'Bounded indexed transfer sample; historical completeness is not established.'}</p></div>
          <div className="flex flex-wrap gap-2 text-xs"><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Page rounds {loadedPages}</span><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Older outgoing {result.next_page_keys?.outgoing ? 'available' : 'none'}</span><span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Older incoming {result.next_page_keys?.incoming ? 'available' : 'none'}</span></div>
        </div>
        {(result.next_page_keys?.outgoing || result.next_page_keys?.incoming) && <button onClick={loadMore} disabled={loadingMore} className="secondary-button mt-4">{loadingMore ? 'Loading older evidence…' : 'Load older transfers'}</button>}
      </section>

      <ScalableBubbleInvestigationGraph
        transactions={records}
        rootAddress={result.root || ''}
        onExpandAddress={expandWallet}
        expandingAddress={expanding}
        expandedAddresses={Object.keys(expansions)}
        nodeContext={nodeContext}
      />

      <p className="text-xs leading-5 text-slate-500">Graph expansion is deliberately bounded to five observed counterparties per investigation. It adds context without claiming complete history, ownership, taint, or intent.</p>
    </>}

    {!result && !loading && !error && <div className="panel p-6 text-sm text-slate-400">Build a wallet graph to load evidence-backed bubbles. No previous wallet graph is reused after a failed or cleared search.</div>}
  </div>;
}
