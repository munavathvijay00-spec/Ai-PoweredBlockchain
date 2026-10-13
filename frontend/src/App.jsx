import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import StatsBar from './components/StatsBar';
import TransactionList from './components/TransactionList';
import TransactionModal from './components/TransactionModal';
import SearchBar from './components/SearchBar';
import FilterTabs from './components/FilterTabs';
import RiskChart from './components/RiskChart';
import WalletGraphWorkspace from './components/WalletGraphWorkspace';
import WalletInvestigator from './components/WalletInvestigator';

const NAV = [
  { id: 'transactions', label: 'Live monitor', icon: '⌁', hint: 'Recent indexed activity' },
  { id: 'wallet', label: 'Wallet intelligence', icon: '◎', hint: 'Address investigation' },
  { id: 'investigate', label: 'Flow workspace', icon: '◇', hint: 'Evidence graph' },
  { id: 'system', label: 'System coverage', icon: '▦', hint: 'Freshness & limits' },
];

function ageLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return 'Unknown';
  if (value < 60) return `${Math.max(0, Math.round(value))}s ago`;
  if (value < 3600) return `${Math.round(value / 60)}m ago`;
  return `${Math.round(value / 3600)}h ago`;
}

function statusTheme(status) {
  if (status === 'live') return 'border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-300';
  if (status === 'delayed') return 'border-amber-400/20 bg-amber-400/[0.07] text-amber-300';
  if (status === 'stale') return 'border-rose-400/20 bg-rose-400/[0.07] text-rose-300';
  return 'border-slate-700 bg-slate-900 text-slate-400';
}

function SystemCoverage({ coverage }) {
  if (!coverage) {
    return <div className="panel p-8 text-sm text-slate-400">Coverage data is not available yet.</div>;
  }

  const health = coverage.ingestion_health || {};
  const readiness = coverage.product_readiness || {};
  const native = coverage.native_transactions || {};
  const checkpoint = coverage.reorg_verification || {};
  const entityIntel = coverage.verified_entity_intelligence || {};
  const entityRecords = Number(entityIntel.records || 0);
  const entityAddresses = Number(entityIntel.unique_addresses || 0);
  const entitySources = Number(entityIntel.sources || 0);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="panel">
          <p className="eyebrow">Indexer</p>
          <p className="mt-3 text-xl font-semibold capitalize text-white">{health.status || 'unknown'}</p>
          <p className="mt-2 text-xs text-slate-500">Checkpoint updated {ageLabel(health.checkpoint_age_seconds)}</p>
        </div>
        <div className="panel">
          <p className="eyebrow">Checkpoint block</p>
          <p className="mt-3 text-xl font-semibold text-cyan-300">{health.checkpoint_block?.toLocaleString?.() || '—'}</p>
          <p className="mt-2 text-xs text-slate-500">Canonical hash recorded: {checkpoint.status === 'checkpoint_hash_recorded' ? 'Yes' : 'No'}</p>
        </div>
        <div className="panel">
          <p className="eyebrow">Retained records</p>
          <p className="mt-3 text-xl font-semibold text-white">{Number(native.stored_transactions || 0).toLocaleString()}</p>
          <p className="mt-2 text-xs text-slate-500">Rolling {readiness.retention_window_minutes || 30} minute native window</p>
        </div>
        <div className="panel">
          <p className="eyebrow">Historical archive</p>
          <p className="mt-3 text-xl font-semibold text-amber-300">{readiness.historical_archive ? 'Available' : 'Not available'}</p>
          <p className="mt-2 text-xs text-slate-500">Coverage is intentionally bounded and explicit</p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Operational scope</p>
              <h3 className="mt-2 text-lg font-semibold text-white">What ChainScope can support today</h3>
            </div>
            <span className={`status-pill ${statusTheme(health.status)}`}>● {health.status || 'unknown'}</span>
          </div>
          <div className="mt-5 space-y-3">
            {(readiness.production_ready_for || []).map(item => (
              <div key={item} className="flex items-start gap-3 rounded-xl border border-emerald-400/10 bg-emerald-400/[0.035] p-3 text-sm text-slate-300">
                <span className="mt-0.5 text-emerald-300">✓</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-5">
          <p className="eyebrow">Known limits</p>
          <h3 className="mt-2 text-lg font-semibold text-white">Do not over-claim these capabilities</h3>
          <div className="mt-5 space-y-3">
            {(readiness.not_ready_for || coverage.limitations || []).map(item => (
              <div key={item} className="flex items-start gap-3 rounded-xl border border-amber-400/10 bg-amber-400/[0.035] p-3 text-sm text-slate-300">
                <span className="mt-0.5 text-amber-300">!</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel p-5">
        <p className="eyebrow">Evidence coverage</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-slate-500">Native transfers</p><p className="mt-2 text-slate-200">Recent retained index</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-slate-500">ERC-20</p><p className="mt-2 text-slate-200">On-demand provider</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-slate-500">Internal traces</p><p className="mt-2 text-rose-300">Not indexed</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4">
            <p className="text-slate-500">Verified entity context</p>
            <p className={`mt-2 ${entityRecords ? 'text-emerald-300' : 'text-amber-300'}`}>
              {entityRecords ? `${entityAddresses.toLocaleString()} addresses · ${entitySources} ${entitySources === 1 ? 'source' : 'sources'}` : 'No local verified records loaded'}
            </p>
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="eyebrow">Entity intelligence registry</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Source-attributed matches only</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Wallet reports and graph nodes can now surface entity context only when ChainScope has a stored, source-attributed verified record for that address. A missing local match is never treated as proof that an address is unknown, safe, or unsanctioned elsewhere.</p>
          </div>
          <span className={`status-pill ${entityRecords ? 'border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-300' : 'border-amber-400/20 bg-amber-400/[0.07] text-amber-300'}`}>
            {entityRecords ? 'Registry available' : 'Registry empty'}
          </span>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-xs text-slate-500">Verified records</p><p className="mt-2 text-xl font-semibold text-white">{entityRecords.toLocaleString()}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-xs text-slate-500">Unique addresses</p><p className="mt-2 text-xl font-semibold text-white">{entityAddresses.toLocaleString()}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/45 p-4"><p className="text-xs text-slate-500">Intelligence sources</p><p className="mt-2 text-xl font-semibold text-white">{entitySources.toLocaleString()}</p></div>
        </div>
        <p className="mt-4 text-xs text-slate-500">Newest source check: {entityIntel.newest_checked_at ? new Date(entityIntel.newest_checked_at).toLocaleString() : 'No verified check recorded'}</p>
      </section>
    </div>
  );
}

function App() {
  const [stats, setStats] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [flagged, setFlagged] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedTx, setSelectedTx] = useState(null);
  const [view, setView] = useState('transactions');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    let active = true;
    let busy = false;

    async function loadData() {
      if (busy || document.visibilityState === 'hidden') return;
      busy = true;
      try {
        const results = await Promise.allSettled([
          api.getStats(),
          api.getCoverage(),
          api.getTransactions(50),
          api.getFlagged(20),
        ]);
        if (!active) return;
        const [statsResult, coverageResult, txsResult, flaggedResult] = results;
        if (statsResult.status === 'fulfilled') setStats(statsResult.value);
        if (coverageResult.status === 'fulfilled') setCoverage(coverageResult.value);
        if (txsResult.status === 'fulfilled') setTransactions(txsResult.value.transactions ?? []);
        if (flaggedResult.status === 'fulfilled') setFlagged(flaggedResult.value.transactions ?? []);
        const failures = results.filter(result => result.status === 'rejected');
        setError(failures.length ? 'Some intelligence services are temporarily unavailable. Latest successful results remain visible.' : null);
        if (failures.length !== results.length) setLastUpdate(new Date());
      } catch {
        if (active) setError('Unable to refresh live intelligence. Retrying automatically.');
      } finally {
        busy = false;
        if (active) setLoading(false);
      }
    }

    loadData();
    const interval = setInterval(loadData, 15000);
    const onVisible = () => { if (document.visibilityState === 'visible') loadData(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  const counts = useMemo(() => ({
    all: transactions.length,
    flagged: flagged.length,
    high: flagged.filter(tx => tx.risk_score >= 40).length,
  }), [transactions, flagged]);

  const filtered = useMemo(() => {
    let list = transactions;
    if (filter === 'flagged') list = flagged;
    else if (filter === 'high') list = flagged.filter(tx => tx.risk_score >= 40);

    if (search.trim()) {
      const s = search.toLowerCase();
      list = list.filter(tx =>
        (tx.hash ?? '').toLowerCase().includes(s) ||
        (tx.from_address ?? '').toLowerCase().includes(s) ||
        (tx.to_address ?? '').toLowerCase().includes(s)
      );
    }
    return list;
  }, [transactions, flagged, filter, search]);

  async function inspectTransaction(tx) {
    setSelectedTx(tx);
    try {
      const details = await api.getTransaction(tx.hash);
      setSelectedTx(current => current?.hash === tx.hash ? details : current);
    } catch {
      // The selected transaction may have expired under retention.
    }
  }

  const health = coverage?.ingestion_health;
  const freshness = health?.status || (error ? 'unknown' : 'unknown');
  const latestIndexedBlock = health?.checkpoint_block || (transactions.length ? Math.max(...transactions.map(tx => Number(tx.block_number) || 0)) : null);
  const activeNav = NAV.find(item => item.id === view) || NAV[0];

  return (
    <div className="min-h-screen text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/5 bg-[#070b14]/88 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3 lg:px-6">
          <button onClick={() => setView('transactions')} className="flex items-center gap-3 text-left">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-200 shadow-[0_0_30px_rgba(34,211,238,0.08)]">C</div>
            <div>
              <div className="text-sm font-semibold tracking-[0.18em] text-white">CHAINSCOPE</div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-slate-600">Ethereum Intelligence</div>
            </div>
          </button>

          <div className="flex items-center gap-2 sm:gap-3">
            <span className={`status-pill hidden sm:inline-flex ${statusTheme(freshness)}`}>
              <span>{freshness === 'live' ? '●' : freshness === 'delayed' ? '◐' : '○'}</span>
              Indexer {freshness}
            </span>
            <div className="hidden text-right md:block">
              <p className="text-xs text-slate-300">Block {latestIndexedBlock ? Number(latestIndexedBlock).toLocaleString() : '—'}</p>
              <p className="text-[10px] text-slate-600">Refreshed {lastUpdate ? lastUpdate.toLocaleTimeString() : '—'}</p>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] gap-6 px-4 py-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:px-6">
        <aside className="hidden lg:block">
          <div className="sticky top-24 space-y-5">
            <div>
              <p className="eyebrow px-3">Workspace</p>
              <nav className="mt-3 space-y-1" aria-label="ChainScope workspace">
                {NAV.map(item => (
                  <button key={item.id} onClick={() => setView(item.id)} className={`nav-button ${view === item.id ? 'nav-button-active' : ''}`}>
                    <span className="grid h-8 w-8 place-items-center rounded-lg border border-white/5 bg-white/[0.025] text-base">{item.icon}</span>
                    <span>
                      <span className="block font-medium">{item.label}</span>
                      <span className="mt-0.5 block text-[10px] text-slate-600">{item.hint}</span>
                    </span>
                  </button>
                ))}
              </nav>
            </div>

            <div className="panel p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="eyebrow">Data trust</p>
                <span className={freshness === 'live' ? 'text-emerald-300' : 'text-amber-300'}>{freshness === 'live' ? '●' : '○'}</span>
              </div>
              <p className="mt-3 text-sm font-medium text-slate-200">Recent-chain monitor</p>
              <p className="mt-2 text-xs leading-5 text-slate-500">30-minute native retention. ERC-20 wallet transfers are queried on demand. Verified entity context appears only when source-attributed local records exist.</p>
              <button onClick={() => setView('system')} className="mt-4 text-xs font-medium text-cyan-300 hover:text-cyan-200">Review system coverage →</button>
            </div>
          </div>
        </aside>

        <main className="min-w-0">
          <div className="mb-5 flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {NAV.map(item => (
              <button key={item.id} onClick={() => setView(item.id)} className={`shrink-0 rounded-xl border px-3 py-2 text-xs ${view === item.id ? 'border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-200' : 'border-slate-800 bg-slate-900/70 text-slate-400'}`}>{item.label}</button>
            ))}
          </div>

          <section className="panel-strong relative mb-5 overflow-hidden px-5 py-5 sm:px-6">
            <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 rounded-full bg-cyan-300/[0.045] blur-3xl" />
            <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="eyebrow">{activeNav.hint}</p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">{activeNav.label}</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                  {view === 'transactions' && 'Monitor recent Ethereum activity, inspect evidence, and move from risk cues to verifiable transaction details.'}
                  {view === 'wallet' && 'Investigate an Ethereum address with bounded transfer coverage, counterparties, behavioral review signals, and source-attributed entity context when available.'}
                  {view === 'investigate' && 'Explore observed transaction relationships without turning graph proximity into an ownership or wrongdoing claim.'}
                  {view === 'system' && 'See exactly what is live, what is partial, and what ChainScope is not yet designed to prove.'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className={`status-pill ${statusTheme(freshness)}`}>Indexer {freshness}</span>
                <span className="status-pill border-slate-700 bg-slate-950/50 text-slate-400">Ethereum mainnet</span>
              </div>
            </div>
          </section>

          {error && (
            <div className="mb-5 rounded-2xl border border-amber-400/15 bg-amber-400/[0.045] p-4 text-sm text-amber-200">
              <span className="font-medium">Partial service availability.</span> {error}
            </div>
          )}

          {loading && <p role="status" className="mb-4 text-sm text-slate-500">Connecting to intelligence services…</p>}

          {view === 'transactions' && (
            <div className="space-y-5">
              <StatsBar stats={stats} coverage={coverage} />

              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
                <section className="panel p-5">
                  <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="eyebrow">Transaction intelligence</p>
                      <h2 className="mt-1 text-lg font-semibold text-white">Recent indexed activity</h2>
                    </div>
                    <span className="text-xs text-slate-500">Auto-refresh · 15s</span>
                  </div>
                  <SearchBar value={search} onChange={setSearch} />
                  <div className="mt-4"><FilterTabs active={filter} onChange={setFilter} counts={counts} /></div>
                </section>

                <section className="panel p-5">
                  <div className="mb-3">
                    <p className="eyebrow">Review distribution</p>
                    <h2 className="mt-1 text-lg font-semibold text-white">Risk-score mix</h2>
                  </div>
                  <RiskChart transactions={transactions} />
                </section>
              </div>

              <TransactionList transactions={filtered} onSelect={inspectTransaction} />
            </div>
          )}

          {view === 'wallet' && <WalletInvestigator />}
          {view === 'investigate' && <WalletGraphWorkspace flagged={flagged} onSelect={inspectTransaction} />}
          {view === 'system' && <SystemCoverage coverage={coverage} />}
        </main>
      </div>

      <footer className="mx-auto max-w-[1600px] px-4 pb-8 pt-3 text-center text-[11px] text-slate-700 lg:px-6">
        CHAINSCOPE · Evidence first · Review indicators are not proof of wrongdoing
      </footer>

      {selectedTx && <TransactionModal tx={selectedTx} onClose={() => setSelectedTx(null)} />}
    </div>
  );
}

export default App;
