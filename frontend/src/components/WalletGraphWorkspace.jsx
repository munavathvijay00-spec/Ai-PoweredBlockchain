import { useState } from 'react';
import { api } from '../api/client';
import FlowGraph3D from './FlowGraph3D';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? value.slice(0, 8) + '…' + value.slice(-6) : '—';

export default function WalletGraphWorkspace({ flagged = [], onSelect }) {
  const [address, setAddress] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadedPages, setLoadedPages] = useState(1);
  const [expansions, setExpansions] = useState({});
  const [expanding, setExpanding] = useState('');
  const [expansionAddress, setExpansionAddress] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

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
    setExpansionAddress('');
    setShowAdvanced(false);
    try {
      const response = await api.getWalletGraph(wallet);
      setResult(response);
    } catch (failure) {
      setError(failure.message || 'Unable to retrieve wallet graph.');
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
        const seen = new Set(previous.edges.map(edge => [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|')));
        const fresh = added.filter(edge => {
          const key = [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        return {
          ...previous,
          edges: [...previous.edges, ...fresh],
          next_page_keys: { outgoing: page.outgoing_next_page_key, incoming: page.incoming_next_page_key },
        };
      });
      setLoadedPages(count => count + 1);
    } catch (failure) {
      setError(failure.message || 'Unable to load older transfers.');
    } finally {
      setLoadingMore(false);
    }
  }

  async function expandCounterparty() {
    const wallet = expansionAddress.trim().toLowerCase();
    if (!result || !VALID.test(wallet)) { setError('Choose a valid observed counterparty address.'); return; }
    const known = new Set((result.edges || []).flatMap(edge => [edge.source?.toLowerCase(), edge.target?.toLowerCase()]));
    if (!known.has(wallet)) { setError('Choose an address already observed in this network.'); return; }
    if (wallet === result.root?.toLowerCase()) { setError('The root wallet is already loaded.'); return; }
    if (expansions[wallet]) { setError('This counterparty has already been expanded.'); return; }
    if (Object.keys(expansions).length >= 5) { setError('Expansion limit reached: five counterparties per investigation.'); return; }
    setExpanding(wallet);
    setError('');
    try {
      const page = await api.getWalletGraph(wallet);
      setResult(previous => {
        const seen = new Set(previous.edges.map(edge => [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|')));
        const fresh = (page.edges || []).filter(edge => {
          const key = [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        const previousNodes = previous.nodes || [];
        const nodeIds = new Set(previousNodes.map(node => node.id?.toLowerCase()));
        const newNodes = (page.nodes || []).filter(node => node.id && !nodeIds.has(node.id.toLowerCase()));
        return { ...previous, edges: [...previous.edges, ...fresh], nodes: [...previousNodes, ...newNodes] };
      });
      setExpansions(previous => ({ ...previous, [wallet]: {
        edges: (page.edges || []).length,
        moreOutgoing: Boolean(page.next_page_keys?.outgoing),
        moreIncoming: Boolean(page.next_page_keys?.incoming),
        verifiedEntityMatches: Number(page.verified_entity_matches || 0),
      } }));
      setExpansionAddress('');
    } catch (failure) {
      setError(failure.message || 'Counterparty expansion failed.');
    } finally {
      setExpanding('');
    }
  }

  const records = result ? (result.edges || []).filter(edge => edge.source && edge.target && edge.tx_hash).map(edge => ({
    hash: edge.tx_hash,
    from_address: edge.source,
    to_address: edge.target,
    value: edge.value,
    asset: edge.asset,
    category: edge.category,
    block_number_hex: edge.block_number_hex,
    evidence_url: edge.evidence_url,
    risk_score: null,
  })) : flagged;

  const verifiedNodes = result ? (result.nodes || []).filter(node => Array.isArray(node.verified_entities) && node.verified_entities.length > 0) : [];
  const expansionCount = Object.keys(expansions).length;
  const observedWallets = result ? [...new Set((result.edges || []).flatMap(edge => [edge.source?.toLowerCase(), edge.target?.toLowerCase()]))].filter(Boolean) : [];
  const expandableWallets = observedWallets.filter(wallet => wallet !== result?.root?.toLowerCase() && !expansions[wallet]).sort();

  function selectTransaction(tx) {
    if (result) {
      window.open(tx.evidence_url || 'https://etherscan.io/tx/' + tx.hash, '_blank', 'noopener,noreferrer');
    } else {
      onSelect?.(tx);
    }
  }

  return <div className="space-y-5">
    <form onSubmit={investigate} className="panel-strong relative overflow-hidden p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-violet-400/[0.055] blur-3xl" />
      <div className="relative">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Evidence network</p>
            <h2 className="mt-2 text-xl font-semibold text-white">Build a bounded fund-flow workspace</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Build an evidence-linked Ethereum transfer graph, load older transfer pages when available, and inspect the underlying transactions directly.</p>
          </div>
          <span className="status-pill border-violet-400/20 bg-violet-400/[0.07] text-violet-300">Read-only graph</span>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input aria-label="Ethereum wallet for graph" value={address} onChange={event => setAddress(event.target.value)} placeholder="0x… Ethereum wallet address" className="soft-input min-w-0 flex-1 font-mono" />
          <button disabled={loading} className="primary-button min-w-36">{loading ? 'Building…' : 'Build network'}</button>
          {result && <button type="button" onClick={() => { setResult(null); setError(''); }} className="secondary-button">Show flagged feed</button>}
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
      </div>
    </form>

    {result && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="panel p-4"><p className="eyebrow">Observed edges</p><p className="mt-3 text-2xl font-semibold text-white">{records.length}</p><p className="mt-2 text-[11px] text-slate-600">Evidence-linked transfers</p></div>
        <div className="panel p-4"><p className="eyebrow">Observed wallets</p><p className="mt-3 text-2xl font-semibold text-cyan-300">{observedWallets.length}</p><p className="mt-2 text-[11px] text-slate-600">Loaded graph only</p></div>
        <div className="panel p-4"><p className="eyebrow">Verified entity matches</p><p className={`mt-3 text-2xl font-semibold ${verifiedNodes.length ? 'text-emerald-300' : 'text-slate-500'}`}>{verifiedNodes.length}</p><p className="mt-2 text-[11px] text-slate-600">Shown only when matched</p></div>
        <div className="panel p-4"><p className="eyebrow">Expanded counterparties</p><p className="mt-3 text-2xl font-semibold text-violet-300">{expansionCount}</p><p className="mt-2 text-[11px] text-slate-600">Optional deeper graph context</p></div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="eyebrow">Root address</p>
            <a href={'https://etherscan.io/address/' + result.root} target="_blank" rel="noopener noreferrer" className="mt-2 block break-all font-mono text-sm text-cyan-300 hover:text-cyan-200">{result.root} ↗</a>
            <p className="mt-2 text-xs leading-5 text-amber-300">{result.scope || 'Bounded indexed transfer sample; historical completeness is not established.'}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Page rounds {loadedPages}</span>
            <span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Outgoing more {result.next_page_keys?.outgoing ? 'yes' : 'no'}</span>
            <span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Incoming more {result.next_page_keys?.incoming ? 'yes' : 'no'}</span>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {(result.next_page_keys?.outgoing || result.next_page_keys?.incoming) && <button onClick={loadMore} disabled={loadingMore} className="secondary-button">{loadingMore ? 'Loading older evidence…' : 'Load older transfers'}</button>}
          {expandableWallets.length > 0 && <button type="button" onClick={() => setShowAdvanced(value => !value)} className="secondary-button">{showAdvanced ? 'Hide advanced expansion' : 'Advanced graph expansion'}</button>}
        </div>

        {showAdvanced && expandableWallets.length > 0 && <div className="mt-4 rounded-xl border border-violet-400/15 bg-violet-400/[0.035] p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-violet-200">Expand one observed counterparty</p>
              <p className="mt-1 text-xs text-slate-500">Useful only when you need one additional hop of evidence around a specific wallet. Maximum five expansions.</p>
            </div>
            <select aria-label="Counterparty to expand" value={expansionAddress} onChange={event => setExpansionAddress(event.target.value)} className="soft-input min-w-0 flex-1 font-mono text-xs">
              <option value="">Choose observed counterparty…</option>
              {expandableWallets.map(wallet => <option key={wallet} value={wallet}>{wallet}</option>)}
            </select>
            <button type="button" onClick={expandCounterparty} disabled={Boolean(expanding) || !expansionAddress || expansionCount >= 5} className="primary-button">{expanding ? 'Expanding…' : 'Expand'}</button>
          </div>
          {expansionCount > 0 && <p className="mt-3 text-xs text-slate-500">Expanded {expansionCount}/5 counterparties. Added edges are merged directly into the graph below.</p>}
        </div>}
      </section>

      {verifiedNodes.length > 0 && <section className="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.035] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">Verified entity matches</span>
          {verifiedNodes.slice(0, 8).flatMap(node => node.verified_entities.map((entity, index) => (
            <a key={`${node.id}-${entity.source}-${entity.entity_id}-${index}`} href={'https://etherscan.io/address/' + node.id} target="_blank" rel="noopener noreferrer" className="rounded-full border border-emerald-400/15 bg-slate-950/50 px-2.5 py-1 text-[11px] text-emerald-200 hover:border-emerald-300/30" title={node.id}>{entity.entity_name || short(node.id)} · {entity.source} ↗</a>
          )))}
        </div>
        <p className="mt-2 text-xs text-slate-500">These are source-attributed address matches only; they do not establish ownership or wrongdoing.</p>
      </section>}
    </>}

    <section className="panel p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div><p className="eyebrow">Graph canvas</p><h3 className="mt-2 text-lg font-semibold text-white">{result ? 'Observed fund-flow evidence' : 'Current flagged activity'}</h3></div>
        <p className="text-xs text-slate-500">Rotate in 3D, inspect aggregated flows, then open underlying transaction evidence</p>
      </div>
      <FlowGraph3D transactions={records} root={result?.root} onSelect={selectTransaction} />
    </section>
  </div>;
}
