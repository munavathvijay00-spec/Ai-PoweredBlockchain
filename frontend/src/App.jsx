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
  { id: 'transactions', label: 'Live monitor' },
  { id: 'wallet', label: 'Wallet intelligence' },
  { id: 'investigate', label: 'Flow workspace' },
  { id: 'system', label: 'System coverage' },
];

function ageLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return 'Unknown';
  if (value < 60) return `${Math.max(0, Math.round(value))}s ago`;
  if (value < 3600) return `${Math.round(value / 60)}m ago`;
  return `${Math.round(value / 3600)}h ago`;
}

function statusMeta(status) {
  if (status === 'live') return { label: 'Live', dot: 'bg-emerald-400', text: 'text-emerald-400' };
  if (status === 'delayed') return { label: 'Delayed', dot: 'bg-amber-400', text: 'text-amber-300' };
  if (status === 'stale') return { label: 'Stale', dot: 'bg-rose-400', text: 'text-rose-300' };
  return { label: 'Unverified', dot: 'bg-slate-500', text: 'text-slate-400' };
}

function SectionHeading({ view, freshness }) {
  const copy = {
    wallet: ['Wallet Intelligence', 'Investigate an Ethereum address with bounded, evidence-backed transfer coverage.'],
    investigate: ['Flow Workspace', 'Explore observed transaction relationships without inferring ownership or wrongdoing.'],
    system: ['System Coverage', 'See freshness, retention, evidence limits, and verified intelligence coverage.'],
  };
  const [title, subtitle] = copy[view] || ['', ''];
  const status = statusMeta(freshness);
  return (
    <div className="section-heading">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <span className={`inline-flex items-center gap-2 text-sm font-medium ${status.text}`}>
        <span className={`h-2 w-2 rounded-full ${status.dot}`} />
        {status.label}
      </span>
    </div>
  );
}

function SystemCoverage({ coverage }) {
  if (!coverage) return <div className="platform-card p-8 text-sm text-slate-400">Coverage data is not available yet.</div>;

  const health = coverage.ingestion_health || {};
  const readiness = coverage.product_readiness || {};
  const native = coverage.native_transactions || {};
  const checkpoint = coverage.reorg_verification || {};
  const entityIntel = coverage.verified_entity_intelligence || {};

  const cards = [
    ['Indexer', health.status || 'unknown', `Checkpoint updated ${ageLabel(health.checkpoint_age_seconds)}`],
    ['Checkpoint block', health.checkpoint_block ? Number(health.checkpoint_block).toLocaleString() : '—', checkpoint.status === 'checkpoint_hash_recorded' ? 'Canonical hash recorded' : 'Canonical hash not verified'],
    ['Retained records', Number(native.stored_transactions || 0).toLocaleString(), `Rolling ${readiness.retention_window_minutes || 30} minute native window`],
    ['Entity records', Number(entityIntel.records || 0).toLocaleString(), `${Number(entityIntel.unique_addresses || 0).toLocaleString()} unique addresses`],
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value, note]) => (
          <div key={label} className="platform-card p-5">
            <p className="metric-label">{label}</p>
            <p className="mt-3 text-2xl font-semibold text-white">{value}</p>
            <p className="mt-2 text-xs text-slate-500">{note}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="platform-card p-5">
          <p className="metric-label">Supported today</p>
          <div className="mt-4 space-y-3">
            {(readiness.production_ready_for || []).map(item => <div key={item} className="coverage-row"><span className="text-emerald-400">✓</span><span>{item}</span></div>)}
          </div>
        </section>
        <section className="platform-card p-5">
          <p className="metric-label">Known limits</p>
          <div className="mt-4 space-y-3">
            {(readiness.not_ready_for || coverage.limitations || []).map(item => <div key={item} className="coverage-row"><span className="text-amber-300">!</span><span>{item}</span></div>)}
          </div>
        </section>
      </div>
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
          api.getStats(), api.getCoverage(), api.getTransactions(50), api.getFlagged(50),
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
        if (active) setError('Unable to refresh blockchain intelligence. Retrying automatically.');
      } finally {
        busy = false;
        if (active) setLoading(false);
      }
    }
    loadData();
    const interval = setInterval(loadData, 15000);
    const onVisible = () => { if (document.visibilityState === 'visible') loadData(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { active = false; clearInterval(interval); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  const counts = useMemo(() => ({
    all: transactions.length,
    flagged: flagged.length,
    high: flagged.filter(tx => Number(tx.risk_score) >= 40).length,
  }), [transactions, flagged]);

  const filtered = useMemo(() => {
    let list = filter === 'flagged' ? flagged : filter === 'high' ? flagged.filter(tx => Number(tx.risk_score) >= 40) : transactions;
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter(tx => [tx.hash, tx.from_address, tx.to_address].some(value => (value || '').toLowerCase().includes(q)));
  }, [transactions, flagged, filter, search]);

  async function inspectTransaction(tx) {
    setSelectedTx(tx);
    try {
      const details = await api.getTransaction(tx.hash);
      setSelectedTx(current => current?.hash === tx.hash ? details : current);
    } catch {
      // Keep the retained row visible if its detailed record expires during inspection.
    }
  }

  const freshness = coverage?.ingestion_health?.status || 'unknown';
  const status = statusMeta(freshness);
  const latestIndexedBlock = coverage?.ingestion_health?.checkpoint_block || (transactions.length ? Math.max(...transactions.map(tx => Number(tx.block_number) || 0)) : null);

  return (
    <div className="min-h-screen bg-[#0d1628] text-slate-100">
      <header className="platform-header">
        <div className="platform-header-inner">
          <button onClick={() => setView('transactions')} className="flex items-center gap-4 text-left">
            <span className="chain-mark" aria-hidden="true"><span /><span /></span>
            <span>
              <span className="block text-[21px] font-semibold tracking-tight text-white sm:text-[25px]">Blockchain Intelligence Platform</span>
              <span className="mt-1 block text-sm text-slate-400 sm:text-base">AI-powered Ethereum transaction analysis</span>
            </span>
          </button>
          <div className="flex items-center gap-6">
            <nav className="hidden xl:flex items-center gap-1" aria-label="Workspace navigation">
              {NAV.map(item => (
                <button key={item.id} onClick={() => setView(item.id)} className={`top-nav-button ${view === item.id ? 'top-nav-button-active' : ''}`}>{item.label}</button>
              ))}
            </nav>
            <div className="min-w-[118px] text-right">
              <div className={`flex items-center justify-end gap-2 text-sm font-medium ${status.text}`}><span className={`h-2 w-2 rounded-full ${status.dot}`} />{status.label}</div>
              <div className="mt-1 text-xs text-slate-500">Updated: {lastUpdate ? lastUpdate.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—'}</div>
            </div>
          </div>
        </div>
      </header>

      <main className="platform-shell">
        <div className="mb-5 flex gap-2 overflow-x-auto xl:hidden">
          {NAV.map(item => <button key={item.id} onClick={() => setView(item.id)} className={`workspace-chip ${view === item.id ? 'workspace-chip-active' : ''}`}>{item.label}</button>)}
        </div>

        {error && <div className="mb-5 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-200">{error}</div>}
        {loading && <p role="status" className="mb-4 text-sm text-slate-500">Connecting to intelligence services…</p>}

        {view === 'transactions' && (
          <div className="space-y-6">
            <StatsBar stats={stats} coverage={coverage} />
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_440px]">
              <div className="space-y-4">
                <SearchBar value={search} onChange={setSearch} />
                <FilterTabs active={filter} onChange={setFilter} counts={counts} />
              </div>
              <RiskChart transactions={transactions} />
            </div>
            <TransactionList transactions={filtered} onSelect={inspectTransaction} />
            <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-xs text-slate-600">
              <span>Ethereum mainnet · Block {latestIndexedBlock ? Number(latestIndexedBlock).toLocaleString() : '—'}</span>
              <span>Risk scores are review signals, not fraud verdicts.</span>
            </div>
          </div>
        )}

        {view !== 'transactions' && <SectionHeading view={view} freshness={freshness} />}
        {view === 'wallet' && <WalletInvestigator />}
        {view === 'investigate' && <WalletGraphWorkspace flagged={flagged} onSelect={inspectTransaction} />}
        {view === 'system' && <SystemCoverage coverage={coverage} />}
      </main>

      <footer className="pb-8 pt-3 text-center text-[11px] text-slate-700">CHAINSCOPE · Evidence first · Review indicators are not proof of wrongdoing</footer>
      {selectedTx && <TransactionModal tx={selectedTx} onClose={() => setSelectedTx(null)} />}
    </div>
  );
}

export default App;
