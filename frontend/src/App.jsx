import { useEffect, useState } from 'react';
import { api } from './api/client';
import StatsBar from './components/StatsBar';
import TransactionList from './components/TransactionList';
import TransactionModal from './components/TransactionModal';
import RiskChart from './components/RiskChart';
import TransactionBrowserControls from './components/TransactionBrowserControls';
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
      <div><h1>{title}</h1><p>{subtitle}</p></div>
      <span className={`inline-flex items-center gap-2 text-sm font-medium ${status.text}`}><span className={`h-2 w-2 rounded-full ${status.dot}`} />{status.label}</span>
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
  const detection = coverage.detection_quality || {};
  const detectionValue = detection.status === 'evaluated' ? `${Math.round(Number(detection.precision || 0) * 100)}% precision` : 'Not measured';
  const cards = [
    ['Indexer', health.status || 'unknown', `Checkpoint updated ${ageLabel(health.checkpoint_age_seconds)}`],
    ['Checkpoint block', health.checkpoint_block ? Number(health.checkpoint_block).toLocaleString() : '—', checkpoint.status === 'checkpoint_hash_recorded' ? 'Canonical hash recorded' : 'Canonical hash not verified'],
    ['Retained records', Number(native.stored_transactions || 0).toLocaleString(), `Rolling ${readiness.retention_window_minutes || 5} minute native window`],
    ['Detection quality', detectionValue, detection.status === 'evaluated' ? 'Independent holdout evaluation' : 'Independent labels required before accuracy claims'],
  ];
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{cards.map(([label, value, note]) => <div key={label} className="platform-card p-5"><p className="metric-label">{label}</p><p className="mt-3 text-2xl font-semibold text-white">{value}</p><p className="mt-2 text-xs text-slate-500">{note}</p></div>)}</div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="platform-card p-5"><p className="metric-label">Supported today</p><div className="mt-4 space-y-3">{(readiness.production_ready_for || []).map(item => <div key={item} className="coverage-row"><span className="text-emerald-400">✓</span><span>{item}</span></div>)}{entityIntel.records > 0 && <div className="coverage-row"><span className="text-emerald-400">✓</span><span>{Number(entityIntel.records).toLocaleString()} source-attributed entity records loaded</span></div>}</div></section>
        <section className="platform-card p-5"><p className="metric-label">Known limits</p><div className="mt-4 space-y-3">{(readiness.not_ready_for || coverage.limitations || []).map(item => <div key={item} className="coverage-row"><span className="text-amber-300">!</span><span>{item}</span></div>)}</div></section>
      </div>
    </div>
  );
}

function App() {
  const [stats, setStats] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [flagged, setFlagged] = useState([]);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [globalError, setGlobalError] = useState(null);
  const [selectedTx, setSelectedTx] = useState(null);
  const [view, setView] = useState('transactions');

  const [search, setSearch] = useState('');
  const [minRisk, setMinRisk] = useState('');
  const [maxRisk, setMaxRisk] = useState('');
  const [minValue, setMinValue] = useState('');
  const [maxValue, setMaxValue] = useState('');
  const [sort, setSort] = useState('newest');
  const [pageSize, setPageSizeState] = useState(50);
  const [page, setPage] = useState(1);
  const [browser, setBrowser] = useState({ transactions: [], total: 0, distribution: null });
  const [browserLoading, setBrowserLoading] = useState(true);
  const [browserError, setBrowserError] = useState(null);
  const [browserRefresh, setBrowserRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    let busy = false;
    async function loadSystem() {
      if (busy || document.visibilityState === 'hidden') return;
      busy = true;
      const results = await Promise.allSettled([api.getStats(), api.getCoverage(), api.getFlagged(50)]);
      if (!active) return;
      const [statsResult, coverageResult, flaggedResult] = results;
      if (statsResult.status === 'fulfilled') setStats(statsResult.value);
      if (coverageResult.status === 'fulfilled') setCoverage(coverageResult.value);
      if (flaggedResult.status === 'fulfilled') setFlagged(flaggedResult.value.transactions ?? []);
      const failures = results.filter(result => result.status === 'rejected');
      setGlobalError(failures.length ? 'Some services are temporarily unavailable. Last successful data remains visible.' : null);
      if (failures.length !== results.length) setLastUpdate(new Date());
      busy = false;
    }
    loadSystem();
    const interval = setInterval(loadSystem, 15000);
    const onVisible = () => { if (document.visibilityState === 'visible') loadSystem(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { active = false; clearInterval(interval); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setBrowserLoading(true);
      setBrowserError(null);
      try {
        const data = await api.getTransactionBrowser({
          limit: pageSize,
          offset: (page - 1) * pageSize,
          search,
          min_risk: minRisk,
          max_risk: maxRisk,
          min_value_eth: minValue,
          max_value_eth: maxValue,
          sort,
        });
        if (active) {
          setBrowser(data);
          setLastUpdate(new Date());
        }
      } catch (error) {
        if (active) setBrowserError(error?.message || 'Unable to load transactions.');
      } finally {
        if (active) setBrowserLoading(false);
      }
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [page, pageSize, search, minRisk, maxRisk, minValue, maxValue, sort, browserRefresh]);

  const totalPages = Math.max(1, Math.ceil(Number(browser.total || 0) / pageSize));
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);

  function resetFilters() {
    setSearch(''); setMinRisk(''); setMaxRisk(''); setMinValue(''); setMaxValue(''); setSort('newest'); setPage(1);
  }

  function setPageSize(value) { setPageSizeState(value); setPage(1); }
  function updateFilter(setter, value) { setter(value); setPage(1); }

  function exportCurrent(format) {
    const url = api.getTransactionExportUrl(format, {
      search, min_risk: minRisk, max_risk: maxRisk, min_value_eth: minValue, max_value_eth: maxValue, sort,
    });
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `chainscope-transactions.${format}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  async function inspectTransaction(tx) {
    setSelectedTx(tx);
    try {
      const details = await api.getTransaction(tx.hash);
      setSelectedTx(current => current?.hash === tx.hash ? details : current);
    } catch {
      // Keep the page row visible if its detail record becomes unavailable.
    }
  }

  const freshness = coverage?.ingestion_health?.status || 'unknown';
  const status = statusMeta(freshness);
  const checkpointAge = coverage?.ingestion_health?.checkpoint_age_seconds;
  const latestIndexedBlock = coverage?.ingestion_health?.checkpoint_block || browser?.newest_block || null;
  const flaggedCount = Number(stats?.flagged_transactions || 0);
  const highReviewCount = Number(stats?.high_risk_transactions || 0);

  return (
    <div className="min-h-screen bg-[#0d1628] text-slate-100">
      <header className="platform-header">
        <div className="platform-header-inner">
          <button onClick={() => setView('transactions')} className="flex items-center gap-4 text-left" aria-label="Open live monitor">
            <span className="chain-mark" aria-hidden="true"><span /><span /></span>
            <span><span className="block text-[21px] font-semibold tracking-tight text-white sm:text-[25px]">Blockchain Intelligence Platform</span><span className="mt-1 block text-sm text-slate-400 sm:text-base">AI-powered Ethereum transaction analysis</span></span>
          </button>
          <div className="flex items-center gap-6">
            <nav className="hidden xl:flex items-center gap-1" aria-label="Workspace navigation">{NAV.map(item => <button key={item.id} onClick={() => setView(item.id)} className={`top-nav-button ${view === item.id ? 'top-nav-button-active' : ''}`}>{item.label}</button>)}</nav>
            <div className="min-w-[130px] text-right" aria-live="polite"><div className={`flex items-center justify-end gap-2 text-sm font-medium ${status.text}`}><span className={`h-2 w-2 rounded-full ${status.dot}`} />{status.label}</div><div className="mt-1 text-xs text-slate-500">Checkpoint {ageLabel(checkpointAge)}</div><div className="mt-0.5 text-[10px] text-slate-600">UI refreshed {lastUpdate ? lastUpdate.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—'}</div></div>
          </div>
        </div>
      </header>

      <main className="platform-shell">
        <div className="mb-5 flex gap-2 overflow-x-auto xl:hidden">{NAV.map(item => <button key={item.id} onClick={() => setView(item.id)} className={`workspace-chip ${view === item.id ? 'workspace-chip-active' : ''}`}>{item.label}</button>)}</div>
        {globalError && <div className="mb-5 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-200" role="status">{globalError}</div>}

        {view === 'transactions' && <div className="space-y-6">
          <section className="overflow-hidden rounded-xl border border-sky-400/15 bg-gradient-to-r from-sky-400/[0.07] via-[#172338] to-violet-400/[0.06]" aria-label="Investigation pulse">
            <div className="flex flex-col gap-4 px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${status.dot}`} /><span className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Investigation Pulse</span></div>
                <p className="mt-2 text-sm text-slate-400">Ethereum evidence stream · live review workspace</p>
              </div>
              <div className="grid grid-cols-2 gap-x-7 gap-y-3 sm:grid-cols-4">
                <div><p className="text-[10px] uppercase tracking-wider text-slate-500">Latest block</p><p className="mt-1 font-mono text-sm font-semibold text-white">{latestIndexedBlock ? Number(latestIndexedBlock).toLocaleString() : '—'}</p></div>
                <div><p className="text-[10px] uppercase tracking-wider text-slate-500">Filtered population</p><p className="mt-1 text-sm font-semibold text-sky-300">{Number(browser.total || 0).toLocaleString()}</p></div>
                <div><p className="text-[10px] uppercase tracking-wider text-slate-500">Review queue</p><p className="mt-1 text-sm font-semibold text-amber-300">{flaggedCount.toLocaleString()}</p></div>
                <div><p className="text-[10px] uppercase tracking-wider text-slate-500">High review</p><p className="mt-1 text-sm font-semibold text-orange-300">{highReviewCount.toLocaleString()}</p></div>
              </div>
              <div className="shrink-0 text-left xl:text-right"><p className={`text-sm font-semibold ${status.text}`}>{status.label}</p><p className="mt-1 text-xs text-slate-500">checkpoint {ageLabel(checkpointAge)}</p></div>
            </div>
          </section>

          <StatsBar stats={stats} coverage={coverage} />
          <TransactionBrowserControls
            search={search} setSearch={v => updateFilter(setSearch, v)}
            minRisk={minRisk} setMinRisk={v => updateFilter(setMinRisk, v)} maxRisk={maxRisk} setMaxRisk={v => updateFilter(setMaxRisk, v)}
            minValue={minValue} setMinValue={v => updateFilter(setMinValue, v)} maxValue={maxValue} setMaxValue={v => updateFilter(setMaxValue, v)}
            sort={sort} setSort={v => updateFilter(setSort, v)} pageSize={pageSize} setPageSize={setPageSize}
            page={page} totalPages={totalPages} onPage={setPage} onReset={resetFilters} onExport={exportCurrent}
          />
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_440px]">
            <div className="platform-card p-5">
              <p className="metric-label">Current population</p>
              <p className="mt-2 text-3xl font-semibold text-white">{Number(browser.total || 0).toLocaleString()}</p>
              <p className="mt-2 text-sm text-slate-400">Retained transactions matching the active filters. Page {page} shows at most {pageSize} rows.</p>
              <div className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-2"><span>Newest matching block: {browser.newest_block ? Number(browser.newest_block).toLocaleString() : '—'}</span><span>Data freshness: {status.label} · checkpoint {ageLabel(checkpointAge)}</span></div>
            </div>
            <RiskChart distribution={browser.distribution} />
          </div>
          <TransactionList transactions={browser.transactions || []} onSelect={inspectTransaction} totalMatches={browser.total} loading={browserLoading} error={browserError} onRetry={() => setBrowserRefresh(value => value + 1)} />
          <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-xs text-slate-500"><span>Ethereum mainnet · Latest indexed block {latestIndexedBlock ? Number(latestIndexedBlock).toLocaleString() : '—'}</span><span>Exports are bounded to 5,000 matching rows and preserve current filters.</span></div>
        </div>}

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
