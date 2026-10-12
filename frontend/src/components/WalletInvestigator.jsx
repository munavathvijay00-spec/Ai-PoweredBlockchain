import { useState } from 'react';
import { api } from '../api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? value.slice(0, 8) + '…' + value.slice(-6) : '—';
const block = 'rounded-2xl border border-slate-700/70 bg-[#0d192c] p-5';

export default function WalletInvestigator() {
  const [address, setAddress] = useState('');
  const [wallet, setWallet] = useState('');
  const [transfers, setTransfers] = useState([]);
  const [report, setReport] = useState(null);
  const [graph, setGraph] = useState(null);
  const [balance, setBalance] = useState(null);
  const [cursors, setCursors] = useState({ outgoing: null, incoming: null });
  const [loading, setLoading] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState('');
  const [partial, setPartial] = useState([]);

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid 0x-prefixed 40-byte Ethereum address.'); return; }
    setLoading(true); setError(''); setPartial([]);
    setWallet(''); setTransfers([]); setReport(null); setGraph(null); setBalance(null);
    setCursors({ outgoing: null, incoming: null });
    const results = await Promise.allSettled([
      api.getWalletTransfers(target),
      api.getWalletGraph(target),
      api.getWalletReport(target),
      api.getWalletBalance(target),
    ]);
    const [tx, g, r, b] = results;
    if (tx.status === 'fulfilled') {
      setTransfers(tx.value.transfers || []);
      setCursors({ outgoing: tx.value.outgoing_next_page_key, incoming: tx.value.incoming_next_page_key });
    }
    if (g.status === 'fulfilled') setGraph(g.value);
    if (r.status === 'fulfilled') setReport(r.value);
    if (b.status === 'fulfilled') setBalance(b.value);
    const failures = results.map((item, index) => item.status === 'rejected' ? ['Transfers', 'Graph', 'Report', 'Balance'][index] : null).filter(Boolean);
    setPartial(failures);
    if (failures.length === results.length) setError('Investigation API unavailable. Check backend deployment and Alchemy configuration.');
    else setWallet(target);
    setLoading(false);
  }

  async function loadMore() {
    if (!wallet || (!cursors.outgoing && !cursors.incoming)) return;
    setMoreLoading(true); setError('');
    try {
      const next = await api.getWalletTransfers(wallet, {
        outgoing_page_key: cursors.outgoing,
        incoming_page_key: cursors.incoming,
      }, { outgoing: Boolean(cursors.outgoing), incoming: Boolean(cursors.incoming) });
      const key = t => [t.hash, t.from_address, t.to_address, t.category, t.asset, t.block_number_hex, t.value].join('|');
      setTransfers(old => {
        const seen = new Set(old.map(key));
        return [...old, ...(next.transfers || []).filter(t => !seen.has(key(t)))];
      });
      setCursors({ outgoing: next.outgoing_next_page_key, incoming: next.incoming_next_page_key });
    } catch (e) {
      setError(e.message || 'Unable to load more transfers');
    } finally { setMoreLoading(false); }
  }

  return <section className="space-y-5">
    <div className={block}>
      <div className="text-[11px] font-bold tracking-[0.2em] text-cyan-400 uppercase">Address intelligence / Ethereum mainnet</div>
      <h2 className="text-2xl font-bold mt-2">Investigate any Ethereum wallet</h2>
      <p className="text-sm text-slate-400 mt-2">Query indexed transfers, inspect verified transaction links, and generate an evidence-based summary. No inferred ownership or unverified risk labels.</p>
      <form onSubmit={investigate} className="flex flex-col sm:flex-row gap-3 mt-5">
        <input aria-label="Ethereum wallet address" value={address} onChange={e => setAddress(e.target.value)} placeholder="0x… Ethereum wallet address" className="flex-1 min-w-0 bg-[#070d1b] border border-slate-600 rounded-xl px-4 py-3 font-mono text-sm focus:outline-none focus:border-cyan-400" />
        <button type="submit" disabled={loading} className="rounded-xl bg-cyan-400 text-slate-950 font-bold px-6 py-3 disabled:opacity-50">{loading ? 'Investigating…' : 'Investigate wallet'}</button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-rose-400">{error}</p>}
      {partial.length > 0 && <p className="mt-3 text-sm text-amber-300">Unavailable endpoints: {partial.join(', ')}. Other results are shown when available.</p>}
    </div>
    {wallet && <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className={block}><p className="text-xs text-slate-400">Wallet</p><p className="font-mono text-cyan-300 mt-2" title={wallet}>{short(wallet)}</p></div>
        <div className={block}><p className="text-xs text-slate-400">Observed transfers loaded</p><p className="text-3xl font-bold mt-2">{transfers.length}</p></div>
        <div className={block}><p className="text-xs text-slate-400">Live ETH balance</p><p className="text-xl font-bold mt-2">{balance?.balance_eth ?? 'Unavailable'} ETH</p><p className="text-xs text-slate-500 mt-1">{balance?.block_number ? 'At block ' + balance.block_number : 'Not verified'}</p></div>
      </div>
      <div className={block}>
        <h3 className="font-bold text-lg">Evidence-linked transfers</h3>
        <p className="text-xs text-amber-300 mt-2">Partial coverage: indexed external ETH and ERC-20 records only. Older history requires pagination; internal calls and NFTs are excluded.</p>
        <div className="overflow-x-auto mt-4"><table className="w-full text-left text-xs"><thead><tr className="text-slate-400 border-b border-slate-700"><th className="py-3 pr-3">Transaction</th><th className="pr-3">From</th><th className="pr-3">To</th><th className="pr-3">Asset</th><th>Value</th></tr></thead><tbody>{transfers.map((t,i) => <tr key={[t.hash,t.from_address,t.to_address,t.asset,i].join('-')} className="border-b border-slate-800"><td className="py-3 pr-3 font-mono">{t.evidence_url ? <a className="text-cyan-300 hover:underline" href={t.evidence_url} target="_blank" rel="noopener noreferrer">{short(t.hash)} ↗</a> : short(t.hash)}</td><td className="pr-3 font-mono">{short(t.from_address)}</td><td className="pr-3 font-mono">{short(t.to_address)}</td><td className="pr-3">{t.asset || t.category || '—'}</td><td>{t.value ?? '—'}</td></tr>)}</tbody></table>{transfers.length === 0 && <p className="text-sm text-slate-500 py-5">No transfer records returned in the requested pages. This does not prove inactivity.</p>}</div>
        {(cursors.outgoing || cursors.incoming) && <button disabled={moreLoading} onClick={loadMore} className="mt-4 border border-cyan-500/50 text-cyan-300 px-4 py-2 rounded-lg disabled:opacity-50">{moreLoading ? 'Loading…' : 'Load older transfers'}</button>}
      </div>
      {graph && <div className={block}><h3 className="text-lg font-bold">Observed relationship graph</h3><p className="text-sm text-slate-400 mt-2">{graph.nodes?.length || 0} addresses · {graph.edges?.length || 0} evidence-backed edges · one hop</p><div className="mt-4 space-y-2 max-h-72 overflow-y-auto">{(graph.edges || []).slice(0, 50).map((edge,i) => <div key={i} className="text-xs font-mono rounded-lg bg-slate-900 p-3 flex flex-wrap gap-2 items-center"><span>{short(edge.source)}</span><span className="text-cyan-400">→</span><span>{short(edge.target)}</span><span className="text-slate-400">{edge.asset} {edge.value ?? ''}</span>{edge.evidence_url && <a href={edge.evidence_url} target="_blank" rel="noopener noreferrer" className="text-cyan-300 ml-auto">Evidence ↗</a>}</div>)}</div><p className="text-xs text-slate-500 mt-3">A recorded transfer is not proof of shared ownership or illicit activity.</p></div>}
      {report && <div className={block}><div className="text-[11px] uppercase tracking-widest text-cyan-400">Investigation report / evidence based</div><h3 className="text-lg font-bold mt-2">Observed activity summary</h3><p className="text-sm text-slate-300 mt-3">{report.summary}</p><p className="text-sm text-slate-400 mt-3">Unique counterparties in sampled pages: {report.unique_counterparties ?? '—'}</p><p className="text-sm text-amber-300 mt-2">Risk assessment: {report.risk_assessment?.status || 'not assessed'}. This is not a forensic attribution.</p><div className="mt-4 text-xs text-slate-400 space-y-1">{(report.limitations || []).map((item,i) => <p key={i}>• {item}</p>)}</div><button onClick={() => { const blob = new Blob([JSON.stringify(report,null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a');a.href=url;a.download='wallet-investigation.json';a.click();URL.revokeObjectURL(url); }} className="mt-4 border border-slate-600 rounded-lg px-4 py-2 text-sm hover:bg-slate-800">Export report JSON</button></div>}
    </>}
  </section>;
}
