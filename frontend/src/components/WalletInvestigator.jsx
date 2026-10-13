import { useState } from 'react';
import { api } from '../api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? value.slice(0, 8) + '…' + value.slice(-6) : '—';
const block = 'rounded-lg border border-slate-700 bg-slate-800 p-5';

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
  const [transferFilter, setTransferFilter] = useState('all');
  const [transferQuery, setTransferQuery] = useState('');
  const [selectedPeer, setSelectedPeer] = useState('');

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) { setError('Enter a valid 0x-prefixed 40-byte Ethereum address.'); return; }
    setLoading(true); setError(''); setPartial([]);
    setWallet(''); setTransfers([]); setReport(null); setGraph(null); setBalance(null); setSelectedPeer(''); setTransferFilter('all'); setTransferQuery('');
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
    if (tx.status === 'rejected' && failures.length < results.length) setError('Transfer history is unavailable; graph, report, or balance may still be shown. Do not interpret zero loaded transfers as inactivity.');
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
        const fresh = (next.transfers || []).filter(t => { const id = key(t); if (seen.has(id)) return false; seen.add(id); return true; });
        return [...old, ...fresh];
      });
      setCursors({ outgoing: cursors.outgoing ? (next.outgoing_next_page_key || null) : null, incoming: cursors.incoming ? (next.incoming_next_page_key || null) : null });
    } catch (e) {
      setError(e.message || 'Unable to load more transfers');
    } finally { setMoreLoading(false); }
  }

  const normalizedWallet = wallet.toLowerCase();
  const filteredTransfers = transfers.filter(tx => {
    const from = (tx.from_address || '').toLowerCase();
    const to = (tx.to_address || '').toLowerCase();
    if (from !== normalizedWallet && to !== normalizedWallet) return false;
    if (transferFilter === 'incoming' && to !== normalizedWallet) return false;
    if (transferFilter === 'outgoing' && from !== normalizedWallet) return false;
    const q = transferQuery.trim().toLowerCase();
    return !q || [tx.hash, tx.from_address, tx.to_address, tx.asset, tx.category].some(value => String(value || '').toLowerCase().includes(q));
  });
  const observedPeers = new Set(transfers.flatMap(tx => {
    const from = (tx.from_address || '').toLowerCase();
    const to = (tx.to_address || '').toLowerCase();
    return from === normalizedWallet ? [to] : to === normalizedWallet ? [from] : [];
  }).filter(value => VALID.test(value) && value !== normalizedWallet));
  const peerFilteredTransfers = filteredTransfers.filter(tx => !selectedPeer || (tx.from_address || '').toLowerCase() === selectedPeer || (tx.to_address || '').toLowerCase() === selectedPeer);

  const counterpartyRows = (() => {
    const peers = new Map();
    for (const tx of transfers) {
      const from = (tx.from_address || '').toLowerCase();
      const to = (tx.to_address || '').toLowerCase();
      const peer = from === normalizedWallet ? to : to === normalizedWallet ? from : '';
      if (!VALID.test(peer) || peer === normalizedWallet) continue;
      const row = peers.get(peer) || { address: peer, incoming: 0, outgoing: 0, assets: new Set(), evidence: null };
      if (to === normalizedWallet && from === peer) row.incoming++;
      if (from === normalizedWallet && to === peer) row.outgoing++;
      if (tx.asset) row.assets.add(tx.asset);
      if (!row.evidence && /^0x[a-fA-F0-9]{64}$/.test(tx.hash || '')) row.evidence = 'https://etherscan.io/tx/' + tx.hash;
      peers.set(peer, row);
    }
    return [...peers.values()].sort((a, b) => b.incoming + b.outgoing - a.incoming - a.outgoing || a.address.localeCompare(b.address));
  })();


  return <section className="space-y-5">
    <div className={block}>
      <div className="text-[11px] font-bold tracking-[0.2em] text-slate-400 uppercase">Wallet lookup · Ethereum mainnet</div>
      <h2 className="text-2xl font-bold mt-2">Ethereum wallet lookup</h2>
      <p className="text-sm text-slate-400 mt-2">Query indexed transfers, inspect verified transaction links, and generate an evidence-based summary. No inferred ownership or unverified risk labels.</p>
      <form onSubmit={investigate} className="flex flex-col sm:flex-row gap-3 mt-5">
        <input aria-label="Ethereum wallet address" value={address} onChange={e => setAddress(e.target.value)} placeholder="0x… Ethereum wallet address" className="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded-xl px-4 py-3 font-mono text-sm focus:outline-none focus:border-blue-400" />
        <button type="submit" disabled={loading} className="rounded-lg bg-blue-500 text-white font-bold px-6 py-3 disabled:opacity-50">{loading ? 'Investigating…' : 'Investigate wallet'}</button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-rose-400">{error}</p>}
      {partial.length > 0 && <p className="mt-3 text-sm text-amber-300">Unavailable endpoints: {partial.join(', ')}. Other results are shown when available.</p>}
    </div>
    {wallet && <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className={block}><p className="text-xs text-slate-400">Wallet</p><p className="font-mono text-blue-400 mt-2" title={wallet}>{short(wallet)}</p></div>
        <div className={block}><p className="text-xs text-slate-400">Observed transfers loaded</p><p className="text-3xl font-bold mt-2">{transfers.length}</p></div>
        <div className={block}><p className="text-xs text-slate-400">Live ETH balance</p><p className="text-xl font-bold mt-2">{balance?.balance_eth ?? 'Unavailable'} ETH</p><p className="text-xs text-slate-500 mt-1">{balance?.block_number ? 'At block ' + balance.block_number : 'Not verified'}</p></div>
      </div>
      <div className={block}>
        <h3 className="font-bold text-lg">Evidence-linked transfers</h3>
        <p className="text-xs text-amber-300 mt-2">Partial coverage: indexed external ETH and ERC-20 records only. Older history requires pagination; internal calls and NFTs are excluded.</p>
        <div className="flex flex-wrap gap-3 items-center mt-4">
          <select aria-label="Transfer direction" value={transferFilter} onChange={event => setTransferFilter(event.target.value)} className="rounded-lg bg-slate-900 border border-slate-600 px-3 py-2 text-sm"><option value="all">All directions</option><option value="incoming">Incoming</option><option value="outgoing">Outgoing</option></select>
          <input aria-label="Filter transfer evidence" value={transferQuery} onChange={event => setTransferQuery(event.target.value)} placeholder="Search hash, wallet, asset…" className="flex-1 min-w-[180px] rounded-lg bg-slate-900 border border-slate-600 px-3 py-2 text-sm" />
          <span className="text-xs text-slate-400">{peerFilteredTransfers.length} matching · {observedPeers.size} observed peers</span>
          {selectedPeer && <button type="button" onClick={() => setSelectedPeer('')} className="text-xs text-cyan-300 hover:underline">Clear peer filter: {short(selectedPeer)} ×</button>}
        </div>
        <div className="overflow-x-auto mt-4"><table className="w-full text-left text-xs"><thead><tr className="text-slate-400 border-b border-slate-700"><th className="py-3 pr-3">Transaction</th><th className="pr-3">From</th><th className="pr-3">To</th><th className="pr-3">Asset</th><th>Value</th></tr></thead><tbody>{peerFilteredTransfers.map((t,i) => <tr key={[t.hash,t.from_address,t.to_address,t.asset,i].join('-')} className="border-b border-slate-800"><td className="py-3 pr-3 font-mono">{/^0x[a-fA-F0-9]{64}$/.test(t.hash || '') ? <a className="text-cyan-300 hover:underline" href={'https://etherscan.io/tx/' + t.hash} target="_blank" rel="noopener noreferrer">{short(t.hash)} ↗</a> : short(t.hash)}</td><td className="pr-3 font-mono">{short(t.from_address)}</td><td className="pr-3 font-mono">{short(t.to_address)}</td><td className="pr-3">{t.asset || t.category || '—'}</td><td>{t.value ?? '—'}</td></tr>)}</tbody></table>{peerFilteredTransfers.length === 0 && <p className="text-sm text-slate-500 py-5">{transfers.length ? 'No transfers match the selected filters.' : 'No transfer records returned in the requested pages. This does not prove inactivity.'}</p>}</div>
        {(cursors.outgoing || cursors.incoming) && <button disabled={moreLoading} onClick={loadMore} className="mt-4 border border-cyan-500/50 text-cyan-300 px-4 py-2 rounded-lg disabled:opacity-50">{moreLoading ? 'Loading…' : 'Load older transfers'}</button>}
      </div>
      {transfers.length > 0 && <div className={block}>
        <h3 className="font-bold text-lg">Observed counterparties</h3>
        <p className="text-xs text-slate-400 mt-2">Ranked by transfer-record frequency in loaded pages only. Counts are directional relative to the investigated wallet; they are not ownership or risk assessments.</p>
        <div className="overflow-x-auto mt-4"><table className="w-full text-left text-xs">
          <thead><tr className="text-slate-400 border-b border-slate-700"><th className="py-3 pr-3">Address</th><th className="pr-3">Received from peer</th><th className="pr-3">Sent to peer</th><th className="pr-3">Assets</th><th>Evidence</th></tr></thead>
          <tbody>{counterpartyRows.slice(0, 15).map(peer => <tr key={peer.address} className="border-b border-slate-700/60">
            <td className="py-3 pr-3 font-mono"><button type="button" onClick={() => { setSelectedPeer(peer.address); setTransferFilter('all'); setTransferQuery(''); }} className="text-sky-300 hover:underline mr-2" title="Filter transfer table to this counterparty">Filter</button><a href={'https://etherscan.io/address/' + peer.address} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline" title={peer.address}>{short(peer.address)} ↗</a></td>
            <td className="pr-3">{peer.incoming}</td><td className="pr-3">{peer.outgoing}</td>
            <td className="pr-3">{[...peer.assets].slice(0, 4).join(', ') || '—'}</td>
            <td>{peer.evidence && <a href={peer.evidence} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline">Transfer ↗</a>}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="text-xs text-slate-500 mt-3">Showing {Math.min(15, counterpartyRows.length)} of {counterpartyRows.length} observed counterparties. Self-transfers are excluded.</p>
      </div>}
      {graph && <div className={block}><h3 className="text-lg font-bold">Observed relationship graph</h3><p className="text-sm text-slate-400 mt-2">{graph.nodes?.length || 0} addresses · {graph.edges?.length || 0} evidence-backed edges · one hop</p><div className="mt-4 space-y-2 max-h-72 overflow-y-auto">{(graph.edges || []).slice(0, 50).map((edge,i) => <div key={i} className="text-xs font-mono rounded-lg bg-slate-900 p-3 flex flex-wrap gap-2 items-center"><span>{short(edge.source)}</span><span className="text-cyan-400">→</span><span>{short(edge.target)}</span><span className="text-slate-400">{edge.asset} {edge.value ?? ''}</span>{/^0x[a-fA-F0-9]{64}$/.test(edge.tx_hash || '') && <a href={'https://etherscan.io/tx/' + edge.tx_hash} target="_blank" rel="noopener noreferrer" className="text-cyan-300 ml-auto">Evidence ↗</a>}</div>)}</div><p className="text-xs text-slate-500 mt-3">A recorded transfer is not proof of shared ownership or illicit activity.</p></div>}
      {report && <div className={block}>
        <h3 className="font-semibold text-lg">Behavioral review signals</h3>
        <p className="text-xs text-slate-400 mt-2">Transparent rules applied to the fetched transaction sample. Not fraud verdicts.</p>
        {(report.behavioral_signals || []).length === 0
          ? <p className="text-sm text-slate-400 mt-3">No supported review signals observed in this sample. This does not establish that the wallet is safe.</p>
          : <div className="mt-3 space-y-3">{report.behavioral_signals.map((signal, i) => <details key={(signal.code || 'signal') + i} className="border border-slate-700 rounded-lg p-3 group">
            <summary className="cursor-pointer list-none flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-slate-100">{signal.title || signal.code || 'Review signal'}</span>
              <span className="text-xs text-slate-400">{signal.observed_count ?? '—'} records · View evidence ▾</span>
            </summary>
            <p className="text-sm text-slate-400 mt-3">{signal.explanation || 'No additional rule explanation provided by the API.'}</p>
            <p className="text-xs text-slate-500 mt-2">Rule identifier: <code className="font-mono">{signal.code || 'Not supplied'}</code></p>
            <div className="mt-3 flex flex-wrap gap-3">{(signal.evidence || []).filter(item => /^0x[a-fA-F0-9]{64}$/.test(item.tx_hash || '')).map(item => <a key={item.tx_hash} href={'https://etherscan.io/tx/' + item.tx_hash} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-400 hover:underline font-mono">{short(item.tx_hash)} ↗</a>)}</div>
            {!(signal.evidence || []).some(item => /^0x[a-fA-F0-9]{64}$/.test(item.tx_hash || '')) && <p className="text-xs text-amber-300 mt-3">No valid transaction evidence hashes supplied for this signal.</p>}
            <p className="text-xs text-slate-500 mt-3">Review indicator only; no independently validated fraud classification.</p>
          </details>)}</div>}
        <p className="text-xs text-amber-300 mt-4">Detection evaluation: {report.detection_quality?.status === 'not_evaluated' ? 'Not evaluated against labeled cases' : (report.detection_quality?.status || 'Unknown')}.</p>
      </div>}
      {report && <div className={block}>
        <h3 className="font-semibold text-lg">Data coverage</h3>
        <p className="text-sm text-slate-300 mt-2">Indexed categories: {(report.coverage_details?.categories || ['external', 'erc20']).join(', ')} · newest first · {report.coverage_details?.page_size_per_direction ?? '—'} records per direction/page.</p>
        <p className="text-sm text-slate-400 mt-2">More outgoing pages: {report.coverage_details?.outgoing_has_more ? 'Yes' : 'No'} · More incoming pages: {report.coverage_details?.incoming_has_more ? 'Yes' : 'No'}.</p>
        <p className="text-xs text-amber-300 mt-2">Complete historical coverage is not established. NFT and internal transaction indexing are not included.</p>
      </div>}
      {report && <div className={block}><div className="text-[11px] uppercase tracking-widest text-cyan-400">Investigation report / evidence based</div><h3 className="text-lg font-bold mt-2">Observed activity summary</h3><p className="text-sm text-slate-300 mt-3">{report.summary}</p><p className="text-sm text-slate-400 mt-3">Unique counterparties in sampled pages: {report.unique_counterparties ?? '—'}</p><p className="text-sm text-amber-300 mt-2">Risk assessment: {report.risk_assessment?.status || 'not assessed'}. This is not a forensic attribution.</p><div className="mt-4 text-xs text-slate-400 space-y-1">{(report.limitations || []).map((item,i) => <p key={i}>• {item}</p>)}</div><button onClick={() => { const blob = new Blob([JSON.stringify(report,null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a');a.href=url;a.download='wallet-investigation.json';a.click();URL.revokeObjectURL(url); }} className="mt-4 border border-slate-600 rounded-lg px-4 py-2 text-sm hover:bg-slate-800">Export report JSON</button></div>}
    </>}
  </section>;
}
