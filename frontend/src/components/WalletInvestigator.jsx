import { useRef, useState } from 'react';
import { api } from '../api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? value.slice(0, 8) + '…' + value.slice(-6) : '—';
const block = 'panel p-5';
const inner = 'rounded-xl border border-slate-800 bg-slate-950/45';
const transferKey = t => [t.hash, t.from_address, t.to_address, t.category, t.asset, t.block_number_hex, t.value].join('|');

function freshnessTheme(status) {
  if (status === 'live') return 'text-emerald-300 border-emerald-400/20 bg-emerald-400/[0.06]';
  if (status === 'delayed') return 'text-amber-300 border-amber-400/20 bg-amber-400/[0.06]';
  if (status === 'stale') return 'text-rose-300 border-rose-400/20 bg-rose-400/[0.06]';
  return 'text-slate-400 border-slate-700 bg-slate-900';
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
  const [transferFilter, setTransferFilter] = useState('all');
  const [transferQuery, setTransferQuery] = useState('');
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
    setLoading(true); setMoreLoading(false); setError(''); setPartial([]);
    setWallet(''); setTransfers([]); setReport(null); setGraph(null); setBalance(null); setCoverage(null);
    setSelectedPeer(''); setTransferFilter('all'); setTransferQuery('');
    setCursors({ outgoing: null, incoming: null });

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
      setTransfers((tx.value.transfers || []).filter(t => {
        if ((t.from_address || '').toLowerCase() !== target.toLowerCase() && (t.to_address || '').toLowerCase() !== target.toLowerCase()) return false;
        const key = transferKey(t);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }));
      setCursors({ outgoing: tx.value.outgoing_next_page_key, incoming: tx.value.incoming_next_page_key });
    }
    if (g.status === 'fulfilled') setGraph(g.value);
    if (r.status === 'fulfilled') setReport(r.value);
    if (b.status === 'fulfilled') setBalance(b.value);
    if (c.status === 'fulfilled') setCoverage(c.value);

    const labels = ['Transfers', 'Graph', 'Report', 'Balance', 'Coverage'];
    const failures = results.map((item, index) => item.status === 'rejected' ? labels[index] : null).filter(Boolean);
    setPartial(failures);
    if (failures.length === results.length) setError('Investigation services are unavailable. Check backend deployment and provider configuration.');
    else setWallet(target);
    if (tx.status === 'rejected' && failures.length < results.length) setError('Transfer history is unavailable; other evidence may still be shown. Do not interpret zero loaded transfers as inactivity.');
    setLoading(false);
  }

  async function loadMore() {
    if (loading || moreLoading || !wallet || (!cursors.outgoing && !cursors.incoming)) return;
    const version = requestVersion.current;
    setMoreLoading(true); setError('');
    try {
      const next = await api.getWalletTransfers(wallet, {
        outgoing_page_key: cursors.outgoing,
        incoming_page_key: cursors.incoming,
      }, { outgoing: Boolean(cursors.outgoing), incoming: Boolean(cursors.incoming) });
      if (version !== requestVersion.current) return;
      setTransfers(old => {
        const seen = new Set(old.map(transferKey));
        const fresh = (next.transfers || []).filter(t => {
          if ((t.from_address || '').toLowerCase() !== wallet.toLowerCase() && (t.to_address || '').toLowerCase() !== wallet.toLowerCase()) return false;
          const id = transferKey(t);
          if (seen.has(id)) return false;
          seen.add(id);
          return true;
        });
        return [...old, ...fresh];
      });
      setCursors({
        outgoing: cursors.outgoing ? (next.outgoing_next_page_key || null) : null,
        incoming: cursors.incoming ? (next.incoming_next_page_key || null) : null,
      });
    } catch (e) {
      if (version === requestVersion.current) setError(e.message || 'Unable to load more transfers');
    } finally {
      if (version === requestVersion.current) setMoreLoading(false);
    }
  }

  function exportEvidenceBundle() {
    if (!wallet) return;
    const sortedTransfers = [...transfers].sort((a, b) => transferKey(a).localeCompare(transferKey(b)));
    const hashes = [...new Set(sortedTransfers.map(t => t.hash).filter(hash => /^0x[a-fA-F0-9]{64}$/.test(hash || '')))].sort();
    const bundle = {
      schema_version: 'chainscope-wallet-evidence-v3',
      exported_at_utc: new Date().toISOString(),
      chain: 'ethereum-mainnet',
      investigated_address: wallet.toLowerCase(),
      source: {
        api_base: 'ChainScope configured API /api/wallets/{address}',
        transfer_endpoint: 'transfers',
        graph_endpoint: 'indexed-graph',
        report_endpoint: 'investigation-report',
        balance_endpoint: 'balance',
        coverage_endpoint: '/api/coverage',
        verification_note: 'Explorer links permit independent verification of transaction hashes; entity context is included only when returned as source-attributed local intelligence. Exported values remain point-in-time API observations.',
      },
      coverage: {
        transfer_records_loaded: sortedTransfers.length,
        outgoing_more_pages_available: Boolean(cursors.outgoing),
        incoming_more_pages_available: Boolean(cursors.incoming),
        unavailable_endpoints: partial,
        historical_completeness: 'not_established',
        indexed_categories: report?.coverage_details?.categories || ['external', 'erc20'],
        excluded_categories: ['internal_calls', 'nfts'],
        indexed_ingestion_freshness: coverage?.ingestion_health?.status || 'unknown',
        checkpoint_block: coverage?.ingestion_health?.checkpoint_block || null,
        checkpoint_age_seconds: coverage?.ingestion_health?.checkpoint_age_seconds ?? null,
        entity_context_scope: report?.coverage_details?.entity_context || 'not_available',
      },
      verified_entity_intelligence: report?.verified_entity_intelligence || null,
      evidence_links: hashes.map(hash => ({ tx_hash: hash, explorer_url: 'https://etherscan.io/tx/' + hash })),
      transfers: sortedTransfers,
      graph: graph || null,
      investigation_report: report || null,
      balance: balance || null,
      limitations: [
        'Only loaded transfer pages are included; further pages may exist.',
        'A transfer does not establish address ownership, identity, or fraud.',
        'Entity context is limited to source-attributed records loaded into ChainScope; no local match does not establish that no attribution exists elsewhere.',
        'This export is a point-in-time API snapshot, not a complete chain archive.',
      ],
    };
    const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chainscope-evidence-' + wallet.toLowerCase() + '.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const normalizedWallet = wallet.toLowerCase();
  const entityIntel = report?.verified_entity_intelligence || null;
  const entityMatches = Array.isArray(entityIntel?.matches) ? entityIntel.matches : [];
  const rootEntityMatches = Array.isArray(entityIntel?.investigated_address_matches) ? entityIntel.investigated_address_matches : [];
  const entityByAddress = (() => {
    const map = new Map();
    for (const item of entityMatches) {
      const key = String(item.address || '').toLowerCase();
      if (!VALID.test(key)) continue;
      const existing = map.get(key) || [];
      existing.push(item);
      map.set(key, existing);
    }
    return map;
  })();

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
    return [...peers.values()].map(row => ({ ...row, verifiedEntities: entityByAddress.get(row.address) || [] }))
      .sort((a, b) => b.incoming + b.outgoing - a.incoming - a.outgoing || a.address.localeCompare(b.address));
  })();

  const analystBrief = (() => {
    if (!report) return null;
    const signals = report.behavioral_signals || [];
    const assets = [...new Set(transfers.map(tx => tx.asset || tx.category).filter(Boolean))];
    const topPeer = counterpartyRows[0];
    const topPeerCount = topPeer ? topPeer.incoming + topPeer.outgoing : 0;
    const concentration = transfers.length ? Math.round((topPeerCount / transfers.length) * 100) : 0;
    const hasMore = Boolean(cursors.outgoing || cursors.incoming);
    const entityMatchedAddresses = Number(entityIntel?.matched_addresses || 0);
    const findings = [
      `${transfers.length} transfer records are loaded across ${counterpartyRows.length} observed counterparties.`,
      `${report.incoming_count ?? '—'} incoming and ${report.outgoing_count ?? '—'} outgoing records appear in the report sample.`,
      assets.length ? `${assets.length} observed asset/category ${assets.length === 1 ? 'type' : 'types'}: ${assets.slice(0, 5).join(', ')}${assets.length > 5 ? '…' : ''}.` : 'No asset labels were returned in the loaded transfer sample.',
    ];
    if (topPeer && transfers.length >= 3) findings.push(`The most frequent observed counterparty represents about ${concentration}% of loaded transfer records; this is concentration, not attribution.`);
    if (entityMatchedAddresses) findings.push(`${entityMatchedAddresses} loaded address ${entityMatchedAddresses === 1 ? 'has' : 'have'} source-attributed entity context in ChainScope's local verified intelligence registry.`);
    else findings.push('No source-attributed local entity match was returned for this bounded sample; that does not establish that external attribution does not exist.');
    if (signals.length) findings.push(`${signals.length} transparent behavioral review ${signals.length === 1 ? 'signal is' : 'signals are'} present and linked to transaction evidence.`);
    else findings.push('No configured behavioral review signal fired in this sample; that does not establish safety.');

    const nextActions = [];
    if (hasMore) nextActions.push('Load older transfer pages before drawing conclusions about historical behavior.');
    if (signals.length) nextActions.push('Open the evidence hashes behind each review signal and verify them independently.');
    if (topPeer) nextActions.push(`Inspect the highest-frequency counterparty ${short(topPeer.address)} and compare direction, assets, transaction evidence, and any source-attributed entity context.`);
    if (entityMatchedAddresses) nextActions.push('Review each entity label together with its stated source and checked timestamp before using it in an investigation conclusion.');
    else nextActions.push('Treat identity, ownership, sanctions exposure, and illicit-purpose questions as unresolved; absence from the local registry is not clearance.');

    return {
      headline: signals.length ? `${signals.length} review ${signals.length === 1 ? 'signal' : 'signals'} need analyst attention` : 'No configured review signal in the loaded sample',
      findings,
      nextActions,
      confidence: hasMore ? 'Partial sample' : 'Bounded sample',
    };
  })();

  return (
    <section className="space-y-5">
      <div className="panel-strong relative overflow-hidden p-5 sm:p-6">
        <div className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-cyan-300/[0.05] blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Investigation command</p>
              <h2 className="mt-2 text-xl font-semibold text-white">Investigate an Ethereum address</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Pull bounded ETH/ERC-20 transfer evidence, counterparties, review signals, graph context, a live balance snapshot, and source-attributed entity context when ChainScope has a verified local record.</p>
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
          <div className={block}>
            <p className="eyebrow">Investigated wallet</p>
            <a href={'https://etherscan.io/address/' + wallet} target="_blank" rel="noopener noreferrer" className="mt-3 block font-mono text-sm text-cyan-300 hover:text-cyan-200" title={wallet}>{short(wallet)} ↗</a>
            <p className="mt-2 text-[11px] text-slate-600">Ethereum mainnet</p>
          </div>
          <div className={block}>
            <p className="eyebrow">Transfers loaded</p>
            <p className="mt-3 text-2xl font-semibold text-white">{transfers.length}</p>
            <p className="mt-2 text-[11px] text-slate-600">{cursors.outgoing || cursors.incoming ? 'More history available' : 'No further page key returned'}</p>
          </div>
          <div className={block}>
            <p className="eyebrow">Observed peers</p>
            <p className="mt-3 text-2xl font-semibold text-violet-300">{observedPeers.size}</p>
            <p className="mt-2 text-[11px] text-slate-600">Loaded pages only</p>
          </div>
          <div className={block}>
            <p className="eyebrow">Live ETH balance</p>
            <p className="mt-3 truncate text-lg font-semibold text-emerald-300">{balance?.balance_eth ?? 'Unavailable'} ETH</p>
            <p className="mt-2 text-[11px] text-slate-600">{balance?.block_number ? 'Block ' + Number(balance.block_number).toLocaleString() : 'Point-in-time check unavailable'}</p>
          </div>
        </div>

        {analystBrief && (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
            <section className="panel-strong overflow-hidden">
              <div className="border-b border-white/5 bg-cyan-300/[0.035] px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="eyebrow text-cyan-400">Analyst copilot · evidence synthesis</p>
                    <h3 className="mt-2 text-xl font-semibold text-white">{analystBrief.headline}</h3>
                  </div>
                  <span className="rounded-full border border-cyan-300/15 bg-cyan-300/[0.06] px-3 py-1 text-xs text-cyan-200">{analystBrief.confidence}</span>
                </div>
              </div>
              <div className="p-5">
                <p className="text-sm leading-6 text-slate-400">This brief organizes observed facts, source-attributed local intelligence, and transparent rules into analyst-ready findings. It does not infer identity, ownership, sanctions status, or criminal intent.</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {analystBrief.findings.map((finding, index) => (
                    <div key={finding} className={`${inner} p-4`}>
                      <div className="flex gap-3">
                        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-cyan-300/[0.08] text-[11px] font-semibold text-cyan-300">{index + 1}</span>
                        <p className="text-sm leading-5 text-slate-300">{finding}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className={block}>
              <p className="eyebrow">Recommended next actions</p>
              <div className="mt-4 space-y-3">
                {analystBrief.nextActions.map((action, index) => (
                  <div key={action} className="flex gap-3 text-sm leading-5 text-slate-300">
                    <span className="mt-0.5 text-cyan-300">{index + 1}.</span>
                    <span>{action}</span>
                  </div>
                ))}
              </div>
              <div className={`mt-5 rounded-xl border p-3 text-xs ${freshnessTheme(coverage?.ingestion_health?.status)}`}>
                Indexer: {coverage?.ingestion_health?.status || 'unknown'} · checkpoint {coverage?.ingestion_health?.checkpoint_block ? Number(coverage.ingestion_health.checkpoint_block).toLocaleString() : '—'}
              </div>
            </section>
          </div>
        )}

        {report && <section className={block}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Verified entity context</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Source-attributed local intelligence</h3>
              <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-500">Only records returned from ChainScope's verified intelligence registry are displayed. No local match is not a statement about external attribution, sanctions status, or risk.</p>
            </div>
            <span className={`status-pill ${entityMatches.length ? 'border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-300' : 'border-slate-700 bg-slate-950/50 text-slate-400'}`}>{entityMatches.length ? `${entityMatches.length} matched record${entityMatches.length === 1 ? '' : 's'}` : 'No local match'}</span>
          </div>
          {rootEntityMatches.length > 0 && <div className="mt-4 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.035] p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-emerald-300">Investigated address match</p>
            <div className="mt-3 flex flex-wrap gap-2">{rootEntityMatches.map((entity, index) => <span key={`${entity.source}-${entity.entity_id}-${index}`} className="rounded-full border border-emerald-400/15 bg-slate-950/55 px-3 py-1.5 text-xs text-emerald-100">{entity.entity_name || entity.entity_id} · {entity.source}{entity.checked_at ? ` · checked ${new Date(entity.checked_at).toLocaleDateString()}` : ''}</span>)}</div>
          </div>}
          {entityMatches.length > 0 && <div className="mt-4 grid gap-3 md:grid-cols-2">{entityMatches.filter(match => String(match.address || '').toLowerCase() !== normalizedWallet).slice(0, 10).map((match, index) => <div key={`${match.address}-${match.source}-${match.entity_id}-${index}`} className={`${inner} p-4`}>
            <div className="flex flex-wrap items-start justify-between gap-2"><a href={'https://etherscan.io/address/' + match.address} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-cyan-300 hover:underline">{short(match.address)} ↗</a><span className="text-[10px] uppercase tracking-wider text-slate-600">counterparty</span></div>
            <p className="mt-2 text-sm font-medium text-slate-200">{match.entity_name || match.entity_id}</p>
            <p className="mt-1 text-xs text-slate-500">Source: {match.source}{match.checked_at ? ` · checked ${new Date(match.checked_at).toLocaleDateString()}` : ''}</p>
          </div>)}</div>}
        </section>}

        <div className={block}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Evidence ledger</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Evidence-linked transfers</h3>
              <p className="mt-2 text-xs leading-5 text-amber-300">External ETH and ERC-20 transfer records only. Older history may require pagination; internal calls and NFTs are excluded.</p>
            </div>
            <span className="text-xs text-slate-500">{peerFilteredTransfers.length} visible · {observedPeers.size} peers</span>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <select aria-label="Transfer direction" value={transferFilter} onChange={event => setTransferFilter(event.target.value)} className="soft-input py-2"><option value="all">All directions</option><option value="incoming">Incoming</option><option value="outgoing">Outgoing</option></select>
            <input aria-label="Filter transfer evidence" value={transferQuery} onChange={event => setTransferQuery(event.target.value)} placeholder="Search hash, wallet, asset…" className="soft-input min-w-[220px] flex-1 py-2" />
            {selectedPeer && <button type="button" onClick={() => setSelectedPeer('')} className="secondary-button py-2 text-xs">Clear peer · {short(selectedPeer)} ×</button>}
          </div>
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[780px] text-left text-xs">
              <thead className="bg-slate-950/70 text-slate-500"><tr><th className="px-4 py-3">Transaction</th><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Asset</th><th className="px-4 py-3">Value</th></tr></thead>
              <tbody>{peerFilteredTransfers.map((t, i) => <tr key={[t.hash, t.from_address, t.to_address, t.asset, i].join('-')} className="border-t border-slate-800/80 transition hover:bg-white/[0.02]"><td className="px-4 py-3 font-mono">{/^0x[a-fA-F0-9]{64}$/.test(t.hash || '') ? <a className="text-cyan-300 hover:underline" href={'https://etherscan.io/tx/' + t.hash} target="_blank" rel="noopener noreferrer">{short(t.hash)} ↗</a> : short(t.hash)}</td><td className="px-4 py-3 font-mono text-slate-400">{short(t.from_address)}</td><td className="px-4 py-3 font-mono text-slate-400">{short(t.to_address)}</td><td className="px-4 py-3 text-slate-300">{t.asset || t.category || '—'}</td><td className="px-4 py-3 text-slate-300">{t.value ?? '—'}</td></tr>)}</tbody>
            </table>
            {peerFilteredTransfers.length === 0 && <p className="px-4 py-6 text-sm text-slate-500">{transfers.length ? 'No transfers match the selected filters.' : 'No transfer records returned in the requested pages. This does not prove inactivity.'}</p>}
          </div>
          {(cursors.outgoing || cursors.incoming) && <button disabled={moreLoading} onClick={loadMore} className="secondary-button mt-4">{moreLoading ? 'Loading older evidence…' : 'Load older transfers'}</button>}
        </div>

        {transfers.length > 0 && <div className={block}>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Counterparty analysis</p><h3 className="mt-2 text-lg font-semibold text-white">Observed counterparties</h3></div><p className="text-xs text-slate-500">Frequency + source-attributed local context</p></div>
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800"><table className="w-full min-w-[900px] text-left text-xs">
            <thead className="bg-slate-950/70 text-slate-500"><tr><th className="px-4 py-3">Address</th><th className="px-4 py-3">Received</th><th className="px-4 py-3">Sent</th><th className="px-4 py-3">Assets</th><th className="px-4 py-3">Entity context</th><th className="px-4 py-3">Evidence</th></tr></thead>
            <tbody>{counterpartyRows.slice(0, 15).map(peer => <tr key={peer.address} className="border-t border-slate-800/80 hover:bg-white/[0.02]"><td className="px-4 py-3 font-mono"><button type="button" onClick={() => { setSelectedPeer(peer.address); setTransferFilter('all'); setTransferQuery(''); }} className="mr-2 text-cyan-300 hover:underline">Filter</button><a href={'https://etherscan.io/address/' + peer.address} target="_blank" rel="noopener noreferrer" className="text-slate-300 hover:text-cyan-200" title={peer.address}>{short(peer.address)} ↗</a></td><td className="px-4 py-3">{peer.incoming}</td><td className="px-4 py-3">{peer.outgoing}</td><td className="px-4 py-3">{[...peer.assets].slice(0, 4).join(', ') || '—'}</td><td className="px-4 py-3">{peer.verifiedEntities.length ? <div className="flex max-w-[250px] flex-wrap gap-1.5">{peer.verifiedEntities.slice(0, 3).map((entity, index) => <span key={`${entity.source}-${entity.entity_id}-${index}`} className="rounded-full border border-emerald-400/15 bg-emerald-400/[0.05] px-2 py-1 text-[10px] text-emerald-200" title={`${entity.entity_name || entity.entity_id} · ${entity.source}`}>{entity.entity_name || entity.entity_id} · {entity.source}</span>)}</div> : <span className="text-slate-600">No local match</span>}</td><td className="px-4 py-3">{peer.evidence && <a href={peer.evidence} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:underline">Transfer ↗</a>}</td></tr>)}</tbody>
          </table></div>
          <p className="mt-3 text-xs text-slate-600">Showing {Math.min(15, counterpartyRows.length)} of {counterpartyRows.length} observed counterparties. Entity labels are source-attributed local records, not ownership or compliance verdicts.</p>
        </div>}

        <div className="grid gap-5 xl:grid-cols-2">
          {report && <div className={block}>
            <p className="eyebrow">Behavior review</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Transparent review signals</h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">Rules applied to the fetched sample. These are review cues, not fraud verdicts.</p>
            {(report.behavioral_signals || []).length === 0
              ? <div className={`${inner} mt-4 p-4 text-sm text-slate-400`}>No configured review signal observed in this sample. This does not establish that the wallet is safe.</div>
              : <div className="mt-4 space-y-3">{report.behavioral_signals.map((signal, i) => <details key={(signal.code || 'signal') + i} className={`${inner} p-4 group`}>
                <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-100">{signal.title || signal.code || 'Review signal'}</span>
                  <span className="text-xs text-slate-500">{signal.observed_count ?? '—'} records · evidence ▾</span>
                </summary>
                <p className="mt-3 text-sm leading-5 text-slate-400">{signal.explanation || 'No additional rule explanation provided by the API.'}</p>
                <p className="mt-2 text-xs text-slate-600">Rule: <code className="font-mono">{signal.code || 'Not supplied'}</code></p>
                <div className="mt-3 flex flex-wrap gap-3">{(signal.evidence || []).filter(item => /^0x[a-fA-F0-9]{64}$/.test(item.tx_hash || '')).map(item => <a key={item.tx_hash} href={'https://etherscan.io/tx/' + item.tx_hash} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-cyan-300 hover:underline">{short(item.tx_hash)} ↗</a>)}</div>
              </details>)}</div>}
            <p className="mt-4 text-xs text-amber-300">Detection quality: {report.detection_quality?.status === 'not_evaluated' ? 'not evaluated against independently labeled cases' : (report.detection_quality?.status || 'unknown')}.</p>
          </div>}

          {report && <div className={block}>
            <p className="eyebrow">Coverage contract</p>
            <h3 className="mt-2 text-lg font-semibold text-white">What this investigation includes</h3>
            <div className="mt-4 space-y-3 text-sm">
              <div className={`${inner} p-4`}><p className="text-slate-500">Categories</p><p className="mt-1 text-slate-200">{(report.coverage_details?.categories || ['external', 'erc20']).join(', ')}</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Pagination</p><p className="mt-1 text-slate-200">Outgoing more: {report.coverage_details?.outgoing_has_more ? 'yes' : 'no'} · Incoming more: {report.coverage_details?.incoming_has_more ? 'yes' : 'no'}</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Entity context</p><p className="mt-1 text-slate-200">{report.coverage_details?.entity_context === 'source_attributed_local_matches_only' ? 'Source-attributed local matches only' : 'Not available'}</p></div>
              <div className={`${inner} p-4`}><p className="text-slate-500">Excluded / incomplete</p><p className="mt-1 text-amber-300">Internal calls, NFTs, complete historical coverage, comprehensive entity attribution</p></div>
            </div>
          </div>}
        </div>

        {graph && <div className={block}>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Relationship evidence</p><h3 className="mt-2 text-lg font-semibold text-white">Observed one-hop graph</h3></div><p className="text-xs text-slate-500">{graph.nodes?.length || 0} addresses · {graph.edges?.length || 0} evidence-backed edges</p></div>
          <div className="mt-4 grid max-h-80 gap-2 overflow-y-auto md:grid-cols-2">{(graph.edges || []).slice(0, 50).map((edge, i) => <div key={i} className={`${inner} flex flex-wrap items-center gap-2 p-3 text-xs font-mono`}><span>{short(edge.source)}</span><span className="text-cyan-400">→</span><span>{short(edge.target)}</span><span className="text-slate-500">{edge.asset} {edge.value ?? ''}</span>{/^0x[a-fA-F0-9]{64}$/.test(edge.tx_hash || '') && <a href={'https://etherscan.io/tx/' + edge.tx_hash} target="_blank" rel="noopener noreferrer" className="ml-auto text-cyan-300">Evidence ↗</a>}</div>)}</div>
          <p className="mt-3 text-xs text-slate-600">A recorded transfer establishes movement between addresses, not shared ownership or illicit activity.</p>
        </div>}

        {report && <div className={block}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="max-w-3xl">
              <p className="eyebrow text-cyan-400">Investigation report · evidence based</p>
              <h3 className="mt-2 text-lg font-semibold text-white">Observed activity summary</h3>
              <p className="mt-3 text-sm leading-6 text-slate-300">{report.summary}</p>
              <p className="mt-2 text-sm text-slate-500">Unique counterparties in sampled pages: {report.unique_counterparties ?? '—'} · Risk assessment: {report.risk_assessment?.status || 'not assessed'} · Verified local entity records: {entityMatches.length}.</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button onClick={() => { const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'wallet-investigation.json'; a.click(); URL.revokeObjectURL(url); }} className="secondary-button">Export report</button>
              <button type="button" onClick={exportEvidenceBundle} className="primary-button">Export evidence bundle</button>
            </div>
          </div>
          <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2">{(report.limitations || []).map((item, i) => <p key={i} className={`${inner} p-3`}>• {item}</p>)}</div>
        </div>}
      </>}
    </section>
  );
}
