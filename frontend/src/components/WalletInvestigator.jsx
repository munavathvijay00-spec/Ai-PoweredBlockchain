import { useRef, useState } from 'react';
import { api } from '../api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? value.slice(0, 8) + '…' + value.slice(-6) : '—';
const panel = 'panel p-5';
const inner = 'rounded-xl border border-slate-800 bg-slate-950/45';
const DEFAULT_CATEGORIES = ['external', 'erc20', 'internal', 'erc721', 'erc1155'];
const transferKey = t => [
  t.unique_id, t.hash, t.from_address, t.to_address, t.category, t.asset,
  t.token_id, t.block_number_hex, t.value,
].join('|');

function freshnessTheme(status) {
  if (status === 'live') return 'text-emerald-300 border-emerald-400/20 bg-emerald-400/[0.06]';
  if (status === 'delayed') return 'text-amber-300 border-amber-400/20 bg-amber-400/[0.06]';
  if (status === 'stale') return 'text-rose-300 border-rose-400/20 bg-rose-400/[0.06]';
  return 'text-slate-400 border-slate-700 bg-slate-900';
}

function transferDisplayValue(tx) {
  if (tx.token_id) return `Token ${tx.token_id}`;
  if (tx.value === null || tx.value === undefined || tx.value === '') return '—';
  return tx.value;
}

export default function WalletInvestigator() {
  const [address, setAddress] = useState('');
  const [wallet, setWallet] = useState('');
  const [transfers, setTransfers] = useState([]);
  const [report, setReport] = useState(null);
  const [graph, setGraph] = useState(null);
  const [balance, setBalance] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [cursors, setCursors] = useState({ outgoing: null, incoming: null });
  const [loading, setLoading] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState('');
  const [partial, setPartial] = useState([]);
  const [direction, setDirection] = useState('all');
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const [selectedPeer, setSelectedPeer] = useState('');
  const requestVersion = useRef(0);

  async function investigate(event) {
    event.preventDefault();
    const target = address.trim();
    if (!VALID.test(target)) {
      setError('Enter a valid 0x-prefixed 40-byte Ethereum address.');
      return;
    }

    const version = ++requestVersion.current;
    setLoading(true);
    setMoreLoading(false);
    setError('');
    setPartial([]);
    setWallet('');
    setTransfers([]);
    setReport(null);
    setGraph(null);
    setBalance(null);
    setCoverage(null);
    setCursors({ outgoing: null, incoming: null });
    setDirection('all');
    setCategory('all');
    setQuery('');
    setSelectedPeer('');

    const results = await Promise.allSettled([
      api.getWalletTransfers(target),
      api.getWalletGraph(target),
      api.getWalletReport(target),
      api.getWalletBalance(target),
      api.getCoverage(),
    ]);
    if (version !== requestVersion.current) return;

    const [tx, g, r, b, c] = results;
    if (tx.status === 'fulfilled') {
      const seen = new Set();
      setTransfers((tx.value.transfers || []).filter(item => {
        const from = (item.from_address || '').toLowerCase();
        const to = (item.to_address || '').toLowerCase();
        if (from !== target.toLowerCase() && to !== target.toLowerCase()) return false;
        const key = transferKey(item);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }));
      setCursors({
        outgoing: tx.value.outgoing_next_page_key || null,
        incoming: tx.value.incoming_next_page_key || null,
      });
    }
    if (g.status === 'fulfilled') setGraph(g.value);
    if (r.status === 'fulfilled') setReport(r.value);
    if (b.status === 'fulfilled') setBalance(b.value);
    if (c.status === 'fulfilled') setCoverage(c.value);

    const names = ['Transfers', 'Graph', 'Report', 'Balance', 'Coverage'];
    const failures = results.map((item, index) => item.status === 'rejected' ? names[index] : null).filter(Boolean);
    setPartial(failures);
    if (failures.length === results.length) {
      setError('Investigation services are unavailable. Check backend deployment and provider configuration.');
    } else {
      setWallet(target);
      if (tx.status === 'rejected') {
        setError('Transfer history is unavailable; other evidence may still be shown. Do not interpret zero loaded transfers as inactivity.');
      }
    }
    setLoading(false);
  }

  async function loadMore() {
    if (!wallet || loading || moreLoading || (!cursors.outgoing && !cursors.incoming)) return;
    const version = requestVersion.current;
    setMoreLoading(true);
    setError('');
    try {
      const next = await api.getWalletTransfers(wallet, {
        outgoing_page_key: cursors.outgoing,
        incoming_page_key: cursors.incoming,
      }, {
        outgoing: Boolean(cursors.outgoing),
        incoming: Boolean(cursors.incoming),
      });
      if (version !== requestVersion.current) return;
      setTransfers(previous => {
        const seen = new Set(previous.map(transferKey));
        const fresh = (next.transfers || []).filter(item => {
          const key = transferKey(item);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        return [...previous, ...fresh];
      });
      setCursors({
        outgoing: cursors.outgoing ? (next.outgoing_next_page_key || null) : null,
        incoming: cursors.incoming ? (next.incoming_next_page_key || null) : null,
      });
    } catch (failure) {
      if (version === requestVersion.current) setError(failure.message || 'Unable to load older evidence.');
    } finally {
      if (version === requestVersion.current) setMoreLoading(false);
    }
  }

  function exportJson(name, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportEvidenceBundle() {
    if (!wallet) return;
    const sortedTransfers = [...transfers].sort((a, b) => transferKey(a).localeCompare(transferKey(b)));
    const hashes = [...new Set(sortedTransfers.map(t => t.hash).filter(hash => /^0x[a-fA-F0-9]{64}$/.test(hash || '')))].sort();
    exportJson(`chainscope-evidence-${wallet.toLowerCase()}.json`, {
      schema_version: 'chainscope-wallet-evidence-v4',
      exported_at_utc: new Date().toISOString(),
      chain: 'ethereum-mainnet',
      investigated_address: wallet.toLowerCase(),
      source: {
        transfer_endpoint: '/api/wallets/{address}/transfers',
        graph_endpoint: '/api/wallets/{address}/indexed-graph',
        report_endpoint: '/api/wallets/{address}/investigation-report',
        coverage_endpoint: '/api/coverage',
        verification_note: 'Explorer links support independent transaction verification. Entity context is included only when returned as source-attributed local intelligence.',
      },
      coverage: {
        transfer_records_loaded: sortedTransfers.length,
        outgoing_more_pages_available: Boolean(cursors.outgoing),
        incoming_more_pages_available: Boolean(cursors.incoming),
        unavailable_endpoints: partial,
        historical_completeness: false,
        indexed_categories: report?.coverage_details?.categories || DEFAULT_CATEGORIES,
        excluded_or_incomplete: ['specialnft', 'complete_evm_call_traces', 'complete_historical_reconstruction'],
        page_size_shared_across_categories: report?.coverage_details?.page_size_shared_across_categories ?? true,
        indexed_ingestion_freshness: coverage?.ingestion_health?.status || 'unknown',
        checkpoint_block: coverage?.ingestion_health?.checkpoint_block || null,
        entity_context_scope: report?.coverage_details?.entity_context || 'not_available',
        detection_quality: report?.detection_quality?.status || 'not_evaluated',
      },
      verified_entity_intelligence: report?.verified_entity_intelligence || null,
      evidence_links: hashes.map(hash => ({ tx_hash: hash, explorer_url: `https://etherscan.io/tx/${hash}` })),
      transfers: sortedTransfers,
      graph: graph || null,
      investigation_report: report || null,
      balance: balance || null,
      limitations: [
        'Only loaded provider pages are included; further pages may exist.',
        'Internal transfer records are not complete EVM call-trace trees.',
        'A transfer does not establish address ownership, identity, sanctions status, or fraud.',
        'Detection rules have no validated real-world accuracy until independently labeled holdout evaluation is completed.',
      ],
    });
  }

  const normalizedWallet = wallet.toLowerCase();
  const categories = report?.coverage_details?.categories || DEFAULT_CATEGORIES;
  const entityIntel = report?.verified_entity_intelligence || {};
  const entityMatches = Array.isArray(entityIntel.matches) ? entityIntel.matches : [];
  const rootEntityMatches = Array.isArray(entityIntel.investigated_address_matches) ? entityIntel.investigated_address_matches : [];
  const entityByAddress = new Map();
  for (const item of entityMatches) {
    const key = String(item.address || '').toLowerCase();
    if (!VALID.test(key)) continue;
    entityByAddress.set(key, [...(entityByAddress.get(key) || []), item]);
  }

  const filteredTransfers = transfers.filter(tx => {
    const from = (tx.from_address || '').toLowerCase();
    const to = (tx.to_address || '').toLowerCase();
    if (from !== normalizedWallet && to !== normalizedWallet) return false;
    if (direction === 'incoming' && to !== normalizedWallet) return false;
    if (direction === 'outgoing' && from !== normalizedWallet) return false;
    if (category !== 'all' && tx.category !== category) return false;
    if (selectedPeer && from !== selectedPeer && to !== selectedPeer) return false;
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [tx.hash, tx.from_address, tx.to_address, tx.asset, tx.category, tx.token_id]
      .some(value => String(value || '').toLowerCase().includes(needle));
  });

  const counterpartyRows = (() => {
    const rows = new Map();
    for (const tx of transfers) {
      const from = (tx.from_address || '').toLowerCase();
      const to = (tx.to_address || '').toLowerCase();
      const peer = from === normalizedWallet ? to : to === normalizedWallet ? from : '';
      if (!VALID.test(peer) || peer === normalizedWallet) continue;
      const row = rows.get(peer) || { address: peer, incoming: 0, outgoing: 0, assets: new Set(), evidence: null };
      if (to === normalizedWallet && from === peer) row.incoming += 1;
      if (from === normalizedWallet && to === peer) row.outgoing += 1;
      if (tx.asset || tx.category) row.assets.add(tx.asset || tx.category);
      if (!row.evidence && /^0x[a-fA-F0-9]{64}$/.test(tx.hash || '')) row.evidence = `https://etherscan.io/tx/${tx.hash}`;
      rows.set(peer, row);
    }
    return [...rows.values()].map(row => ({ ...row, verifiedEntities: entityByAddress.get(row.address) || [] }))
      .sort((a, b) => (b.incoming + b.outgoing) - (a.incoming + a.outgoing) || a.address.localeCompare(b.address));
  })();

  const observedPeers = counterpartyRows.length;
  const signals = report?.behavioral_signals || [];
  const hasMore = Boolean(cursors.outgoing || cursors.incoming);

  return (
    <section className="space-y-5">
      <div className="panel-strong relative overflow-hidden p-5 sm:p-6">
        <div className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-cyan-300/[0.05] blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Investigation command</p>
              <h2 className="mt-2 text-xl font-semibold text-white">Investigate an Ethereum address</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Pull bounded external and internal ETH movements, ERC-20, ERC-721 and ERC-1155 transfer evidence, counterparties, transparent review signals, graph context, live balance, and source-attributed entity context.</p>
            </div>
            <div className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1.5 text-[11px] text-slate-400">Read-only · Mainnet</div>
          </div>
          <form onSubmit={investigate} className="mt-5 flex flex-col gap-3 sm:flex-row">
            <input aria-label="Ethereum wallet address" value={address} onChange={e => setAddress(e.target.value)} placeholder="0x… Ethereum wallet address" className="soft-input min-w-0 flex-1 font-mono" />
            <button type="submit" disabled={loading} className="primary-button min-w-40">{loading ? 'Investigating…' : 'Run investigation'}</button>
          </form>
          {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
          {partial.length > 0 && <p className="mt-3 text-xs text-amber-300">Partial result · unavailable: {partial.join(', ')}. Available evidence is still shown.</p>}
        </div>
      </div>

      {wallet && <>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div className={panel}>
            <p className="eyebrow">Investigated wallet</p>
            <a href={`https://etherscan.io/address/${wallet}`} target="_blank" rel="noopener noreferrer" className="mt-3 block font-mono text-sm text-cyan-300 hover:text-cyan-200" title={wallet}>{short(wallet)} ↗</a>
            <p className="mt-2 text-[11px] text-slate-600">Ethereum mainnet</p>
          </div>
          <div className={panel}>
            <p className="eyebrow">Transfers loaded</p>
            <p className="mt-3 text-2xl font-semibold text-white">{transfers.length}</p>
            <p className="mt-2 text-[11px] text-slate-600">{hasMore ? 'Older provider pages available' : 'No further page key returned'}</p>
          </div>
          <div className={panel}>
            <p className="eyebrow">Observed peers</p>
            <p className="mt-3 text-2xl font-semibold text-violet-300">{observedPeers}</p>
            <p className="mt-2 text-[11px] text-slate-600">Loaded pages only</p>
          </div>
          <div className={panel}>
            <p className="eyebrow">Live ETH balance</p>
            <p className="mt-3 truncate text-lg font-semibold text-emerald-300">{balance?.balance_eth ?? 'Unavailable'} ETH</p>
            <p className="mt-2 text-[11px] text-slate-600">{balance?.block_number ? `Block ${Number(balance.block_number).toLocaleString()}` : 'Point-in-time check unavailable'}</p>
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
          <section className="panel-strong overflow-hidden">
            <div className="border-b border-white/5 bg-cyan-300/[0.035] px-5 py-4">
              <p className="eyebrow text-cyan-400">Analyst copilot · bounded evidence synthesis</p>
              <h3 className="mt-2 text-xl font-semibold text-white">{signals.length ? `${signals.length} review signal${signals.length === 1 ? '' : 's'} need attention` : 'No configured review signal in the loaded sample'}</h3>
            </div>
            <div className="grid gap-3 p-5 md:grid-cols-2">
              <div className={`${inner} p-4`}><p className="text-xs text-slate-500">Observed sample</p><p className="mt-2 text-sm text-slate-200">{transfers.length} records · {observedPeers} counterparties · {categories.length} selected provider categories</p></div>
              <div className={`${inner} p-4`}><p className="text-xs text-slate-500">Entity context</p><p className="mt-2 text-sm text-slate-200">{entityIntel.matched_addresses || 0} locally matched address{Number(entityIntel.matched_addresses || 0) === 1 ? '' : 'es'}</p></div>
              <div className={`${inner} p-4`}><p className="text-xs text-slate-500">Historical confidence</p><p className="mt-2 text-sm text-amber-200">{hasMore ? 'Partial sample · older pages remain' : 'Bounded sample · completeness not established'}</p></div>
              <div className={`${inner} p-4`}><p className="text-xs text-slate-500">Detection quality</p><p className="mt-2 text-sm text-amber-200">{report?.detection_quality?.status === 'not_evaluated' ? 'Not independently evaluated' : (report?.detection_quality?.status || 'Unknown')}</p></div>
            </div>
          </section>
          <section className={panel}>
            <p className="eyebrow">Scope guardrails</p>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <p>• Internal records are provider-indexed value transfers, not full EVM call traces.</p>
              <p>• Entity labels are source-attributed local records, not ownership or compliance verdicts.</p>
              <p>• Review signals are deterministic cues, not validated fraud predictions.</p>
              <p>• No result should be interpreted as a complete wallet history.</p>
            </div>
            <div className={`mt-5 rounded-xl border p-3 text-xs ${freshnessTheme(coverage?.ingestion_health?.status)}`}>Indexer: {coverage?.ingestion_health?.status || 'unknown'} · checkpoint {coverage?.ingestion_health?.checkpoint_block ? Number(coverage.ingestion_health.checkpoint_block).toLocaleString() : '—'}</div>
          </section>
        </div>

        <section className={panel}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Evidence ledger</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Evidence-linked transfers</h3>
              <p className="mt-2 text-xs leading-5 text-amber-300">Provider-indexed external/internal ETH, ERC-20, ERC-721 and ERC-1155 records. Older history may require pagination; complete EVM trace trees and provider-specific specialnft records are outside this view.</p>
            </div>
            <span className="text-xs text-slate-500">{filteredTransfers.length} visible · {observedPeers} peers</span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-[150px_180px_minmax(220px,1fr)]">
            <select aria-label="Transfer direction" value={direction} onChange={event => setDirection(event.target.value)} className="soft-input py-2"><option value="all">All directions</option><option value="incoming">Incoming</option><option value="outgoing">Outgoing</option></select>
            <select aria-label="Transfer category" value={category} onChange={event => setCategory(event.target.value)} className="soft-input py-2"><option value="all">All categories</option>{categories.map(item => <option key={item} value={item}>{item}</option>)}</select>
            <input aria-label="Filter transfer evidence" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search hash, wallet, asset, token ID…" className="soft-input py-2" />
          </div>
          {selectedPeer && <button type="button" onClick={() => setSelectedPeer('')} className="secondary-button mt-3 py-2 text-xs">Clear peer · {short(selectedPeer)} ×</button>}
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[900px] text-left text-xs">
              <thead className="bg-slate-950/70 text-slate-500"><tr><th className="px-4 py-3">Transaction</th><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Category / asset</th><th className="px-4 py-3">Value / token</th></tr></thead>
              <tbody>{filteredTransfers.map((tx, index) => <tr key={`${transferKey(tx)}-${index}`} className="border-t border-slate-800/80 transition hover:bg-white/[0.02]">
                <td className="px-4 py-3 font-mono">{/^0x[a-fA-F0-9]{64}$/.test(tx.hash || '') ? <a href={`https://etherscan.io/tx/${tx.hash}`} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline">{short(tx.hash)} ↗</a> : short(tx.hash)}</td>
                <td className="px-4 py-3 font-mono text-slate-400">{short(tx.from_address)}</td>
                <td className="px-4 py-3 font-mono text-slate-400">{short(tx.to_address)}</td>
                <td className="px-4 py-3 text-slate-300"><span className="mr-2 rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">{tx.category || 'unknown'}</span>{tx.asset || '—'}</td>
                <td className="max-w-[240px] truncate px-4 py-3 text-slate-300" title={String(transferDisplayValue(tx))}>{transferDisplayValue(tx)}</td>
              </tr>)}</tbody>
            </table>
            {filteredTransfers.length === 0 && <p className="px-4 py-6 text-sm text-slate-500">{transfers.length ? 'No transfers match the selected filters.' : 'No records returned in the requested pages. This does not prove inactivity.'}</p>}
          </div>
          {hasMore && <button type="button" disabled={moreLoading} onClick={loadMore} className="secondary-button mt-4">{moreLoading ? 'Loading older evidence…' : 'Load older transfers'}</button>}
        </section>

        {counterpartyRows.length > 0 && <section className={panel}>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Counterparty analysis</p><h3 className="mt-2 text-lg font-semibold text-white">Observed counterparties</h3></div><p className="text-xs text-slate-500">Frequency in loaded pages · local entity context where available</p></div>
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800"><table className="w-full min-w-[900px] text-left text-xs">
            <thead className="bg-slate-950/70 text-slate-500"><tr><th className="px-4 py-3">Address</th><th className="px-4 py-3">Received</th><th className="px-4 py-3">Sent</th><th className="px-4 py-3">Assets</th><th className="px-4 py-3">Entity context</th><th className="px-4 py-3">Evidence</th></tr></thead>
            <tbody>{counterpartyRows.slice(0, 15).map(peer => <tr key={peer.address} className="border-t border-slate-800/80 hover:bg-white/[0.02]">
              <td className="px-4 py-3 font-mono"><button type="button" onClick={() => { setSelectedPeer(peer.address); setDirection('all'); setCategory('all'); setQuery(''); }} className="mr-2 text-cyan-300 hover:underline">Filter</button><a href={`https://etherscan.io/address/${peer.address}`} target="_blank" rel="noopener noreferrer" className="text-slate-300 hover:text-cyan-200">{short(peer.address)} ↗</a></td>
              <td className="px-4 py-3">{peer.incoming}</td><td className="px-4 py-3">{peer.outgoing}</td><td className="px-4 py-3">{[...peer.assets].slice(0, 4).join(', ') || '—'}</td>
              <td className="px-4 py-3">{peer.verifiedEntities.length ? peer.verifiedEntities.slice(0, 2).map((entity, index) => <span key={`${entity.source}-${entity.entity_id}-${index}`} className="mr-1 inline-block rounded-full border border-emerald-400/15 bg-emerald-400/[0.05] px-2 py-1 text-[10px] text-emerald-200">{entity.entity_name || entity.entity_id} · {entity.source}</span>) : <span className="text-slate-600">No local match</span>}</td>
              <td className="px-4 py-3">{peer.evidence && <a href={peer.evidence} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline">Transfer ↗</a>}</td>
            </tr>)}</tbody>
          </table></div>
        </section>}

        <div className="grid gap-5 xl:grid-cols-2">
          {report && <section className={panel}>
            <p className="eyebrow">Behavior review</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Transparent review signals</h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">Rules applied to the fetched sample. These are review cues, not fraud verdicts.</p>
            {signals.length === 0 ? <div className={`${inner} mt-4 p-4 text-sm text-slate-400`}>No configured review signal observed. That does not establish that the wallet is safe.</div> : <div className="mt-4 space-y-3">{signals.map((signal, index) => <details key={`${signal.code}-${index}`} className={`${inner} p-4`}>
              <summary className="cursor-pointer font-medium text-slate-100">{signal.title || signal.code} · {signal.observed_count ?? '—'} records</summary>
              <p className="mt-3 text-sm text-slate-400">{signal.explanation}</p>
              <div className="mt-3 flex flex-wrap gap-2">{(signal.evidence || []).map(item => <a key={item.tx_hash} href={item.url || `https://etherscan.io/tx/${item.tx_hash}`} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-cyan-300 hover:underline">{short(item.tx_hash)} ↗</a>)}</div>
            </details>)}</div>}
            <p className="mt-4 text-xs text-amber-300">Detection quality: {report.detection_quality?.status === 'not_evaluated' ? 'not evaluated on an independently labeled representative holdout set' : (report.detection_quality?.status || 'unknown')}.</p>
          </section>}

          {report && <section className={panel}>
            <p className="eyebrow">Coverage contract</p>
            <h3 className="mt-2 text-lg font-semibold text-white">What this investigation includes</h3>
            <div className="mt-4 space-y-3 text-sm">
              <div className={`${inner} p-4`}><p className="text-slate-500">Selected categories</p><p className="mt-1 text-slate-200">{categories.join(', ')}</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Pagination</p><p className="mt-1 text-slate-200">Outgoing more: {report.coverage_details?.outgoing_has_more ? 'yes' : 'no'} · Incoming more: {report.coverage_details?.incoming_has_more ? 'yes' : 'no'} · page size shared across categories</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Entity context</p><p className="mt-1 text-slate-200">Source-attributed local matches only</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Excluded / incomplete</p><p className="mt-1 text-amber-300">Complete EVM call traces, specialnft, complete historical reconstruction, comprehensive entity attribution</p></div>
            </div>
          </section>}
        </div>

        {graph && <section className={panel}>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Relationship evidence</p><h3 className="mt-2 text-lg font-semibold text-white">Observed one-hop graph</h3></div><p className="text-xs text-slate-500">{graph.nodes?.length || 0} addresses · {graph.edges?.length || 0} evidence-backed edges</p></div>
          <div className="mt-4 grid max-h-80 gap-2 overflow-y-auto md:grid-cols-2">{(graph.edges || []).slice(0, 50).map((edge, index) => <div key={`${edge.tx_hash}-${edge.token_id || ''}-${index}`} className={`${inner} flex flex-wrap items-center gap-2 p-3 text-xs font-mono`}><span>{short(edge.source)}</span><span className="text-cyan-400">→</span><span>{short(edge.target)}</span><span className="text-slate-500">{edge.category || edge.asset} {edge.token_id ? `#${edge.token_id}` : (edge.value ?? '')}</span>{/^0x[a-fA-F0-9]{64}$/.test(edge.tx_hash || '') && <a href={`https://etherscan.io/tx/${edge.tx_hash}`} target="_blank" rel="noopener noreferrer" className="ml-auto text-cyan-300">Evidence ↗</a>}</div>)}</div>
          <p className="mt-3 text-xs text-slate-600">A recorded transfer establishes movement between addresses, not common ownership, beneficial ownership, or illicit activity.</p>
        </section>}

        {report && <section className={panel}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="max-w-3xl">
              <p className="eyebrow text-cyan-400">Investigation report · evidence based</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Observed activity summary</h3>
              <p className="mt-3 text-sm leading-6 text-slate-300">{report.summary}</p>
              <p className="mt-2 text-sm text-slate-500">Unique counterparties: {report.unique_counterparties ?? '—'} · Risk assessment: {report.risk_assessment?.status || 'not assessed'} · Verified local entity records: {entityMatches.length}.</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button type="button" onClick={() => exportJson('wallet-investigation.json', report)} className="secondary-button">Export report</button>
              <button type="button" onClick={exportEvidenceBundle} className="primary-button">Export evidence bundle</button>
            </div>
          </div>
          <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2">{(report.limitations || []).map((item, index) => <p key={`${item}-${index}`} className={`${inner} p-3`}>• {item}</p>)}</div>
        </section>}
      </>}
    </section>
  );
}
