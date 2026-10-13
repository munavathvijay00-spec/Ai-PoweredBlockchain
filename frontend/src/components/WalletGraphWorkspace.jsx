import { useState } from 'react';
import { api } from '../api/client';
import InvestigationGraph from './InvestigationGraph';

const VALID = /^0x[a-fA-F0-9]{40}$/;

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
        source: tx.from_address, target: tx.to_address, tx_hash: tx.hash,
        value: tx.value, asset: tx.asset, category: tx.category,
        block_number_hex: tx.block_number_hex, evidence_url: tx.evidence_url,
      }));
      setResult(previous => {
        const seen = new Set(previous.edges.map(edge => [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|')));
        const fresh = added.filter(edge => {
          const key = [edge.tx_hash, edge.source?.toLowerCase(), edge.target?.toLowerCase(), edge.asset, edge.category, edge.value].join('|');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        return { ...previous, edges: [...previous.edges, ...fresh],
          next_page_keys: { outgoing: page.outgoing_next_page_key, incoming: page.incoming_next_page_key } };
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
    if (!result || !VALID.test(wallet)) { setError('Enter a valid counterparty address.'); return; }
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
        return { ...previous, edges: [...previous.edges, ...fresh] };
      });
      setExpansions(previous => ({ ...previous, [wallet]: {
        edges: (page.edges || []).length,
        moreOutgoing: Boolean(page.next_page_keys?.outgoing),
        moreIncoming: Boolean(page.next_page_keys?.incoming),
      } }));
      setExpansionAddress('');
    } catch (failure) {
      setError(failure.message || 'Counterparty expansion failed.');
    } finally { setExpanding(''); }
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

  function selectTransaction(tx) {
    if (result) {
      window.open(tx.evidence_url || 'https://etherscan.io/tx/' + tx.hash, '_blank', 'noopener,noreferrer');
    } else {
      onSelect?.(tx);
    }
  }

  return <div className="mb-7 space-y-4">
    <form onSubmit={investigate} className="rounded-lg border border-slate-700 bg-slate-800 p-5">
      <h2 className="text-lg font-semibold">Investigate wallet connections</h2>
      <p className="text-sm text-slate-400 mt-1">Enter an Ethereum address to build a one-hop network from indexed transfers, or inspect the current flagged feed below.</p>
      <div className="flex flex-wrap gap-3 mt-4">
        <input aria-label="Ethereum wallet for graph" value={address} onChange={event => setAddress(event.target.value)} placeholder="0x… Ethereum wallet address"
          className="min-w-[220px] flex-1 bg-slate-900 border border-slate-600 rounded-lg px-4 py-3 text-sm font-mono focus:outline-none focus:border-blue-400" />
        <button disabled={loading} className="bg-blue-500 hover:bg-blue-400 disabled:opacity-50 rounded-lg px-5 py-3 text-sm font-medium">{loading ? 'Loading…' : 'Build network'}</button>
        {result && <button type="button" onClick={() => { setResult(null); setError(''); }} className="border border-slate-600 rounded-lg px-4 py-3 text-sm">Show flagged feed</button>}
      </div>
      {error && <p role="alert" className="text-rose-400 text-sm mt-3">{error}</p>}
    </form>
    {result && <div className="rounded-lg border border-slate-700 bg-slate-800 p-4 text-sm">
      <p className="text-slate-200">Wallet: <span className="font-mono break-all text-blue-400">{result.root}</span></p>
      <p className="text-slate-400 mt-2">{records.length} observed transfers · one-hop graph · Ethereum mainnet</p>
      <p className="text-amber-300 text-xs mt-2">{result.scope || 'Bounded indexed transfer sample; historical completeness is not established.'}</p>
      <p className="text-slate-400 text-xs mt-2">Loaded page rounds: {loadedPages}. More pages: outgoing {result.next_page_keys?.outgoing ? 'yes' : 'no'}, incoming {result.next_page_keys?.incoming ? 'yes' : 'no'}.</p>
      {(result.next_page_keys?.outgoing || result.next_page_keys?.incoming) && <button onClick={loadMore} disabled={loadingMore} className="mt-3 rounded-lg border border-sky-500/50 text-sky-300 px-4 py-2 text-sm disabled:opacity-50">{loadingMore ? 'Loading older transfers…' : 'Load older transfers into graph'}</button>}
      <div className="border-t border-slate-700 mt-4 pt-4">
        <h3 className="font-semibold text-slate-100">Expand to a second hop</h3>
        <p className="text-xs text-slate-400 mt-1">Select a counterparty already observed in the graph. Up to five explicit expansions; each fetches a bounded first page, not full history.</p>
        <div className="flex flex-wrap gap-2 mt-3">
          <select aria-label="Counterparty to expand" value={expansionAddress} onChange={event => setExpansionAddress(event.target.value)}
            className="flex-1 min-w-[210px] bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-xs font-mono">
            <option value="">Choose observed counterparty…</option>
            {[...new Set((result.edges || []).flatMap(edge => [edge.source?.toLowerCase(), edge.target?.toLowerCase()]))]
              .filter(wallet => wallet && wallet !== result.root?.toLowerCase() && !expansions[wallet])
              .sort().map(wallet => <option key={wallet} value={wallet}>{wallet}</option>)}
          </select>
          <button type="button" onClick={expandCounterparty} disabled={Boolean(expanding) || !expansionAddress || Object.keys(expansions).length >= 5}
            className="rounded-lg bg-sky-700 px-4 py-2 text-sm disabled:opacity-50">{expanding ? 'Expanding…' : 'Expand wallet'}</button>
        </div>
        {Object.keys(expansions).length > 0 && <div className="mt-3 space-y-1 text-xs text-slate-400">
          {Object.entries(expansions).map(([wallet, info]) => <p key={wallet} className="break-all">{wallet}: {info.edges} indexed records queried; more pages {info.moreOutgoing || info.moreIncoming ? 'available but not fetched' : 'not indicated'}</p>)}
        </div>}
      </div>
    </div>}
    <InvestigationGraph transactions={records} onSelect={selectTransaction} />
  </div>;
}
