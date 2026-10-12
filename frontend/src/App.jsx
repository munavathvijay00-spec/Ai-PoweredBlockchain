import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import StatsBar from './components/StatsBar';
import TransactionList from './components/TransactionList';
import TransactionModal from './components/TransactionModal';
import SearchBar from './components/SearchBar';
import FilterTabs from './components/FilterTabs';
import RiskChart from './components/RiskChart';
import InvestigationGraph from './components/InvestigationGraph';
import ActivityPanel from './components/ActivityPanel';
import { downloadTransactions } from './utils/investigation';

function App() {
  const [stats, setStats] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [flagged, setFlagged] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [selectedTx, setSelectedTx] = useState(null);
  const [view, setView] = useState('investigate');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [watchlist, setWatchlist] = useState(() => {
    try { return JSON.parse(localStorage.getItem('chainscope-watchlist') || '[]'); } catch { return []; }
  });
  const [watchOnly, setWatchOnly] = useState(false);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let active = true;
    let busy = false;

    async function loadData() {
      if (busy || document.visibilityState === 'hidden') return;
      busy = true;
      try {
        const results = await Promise.allSettled([
          api.getStats(),
          api.getTransactions(50),
          api.getFlagged(20),
        ]);
        if (!active) return;
        const [statsResult, txsResult, flaggedResult] = results;
        if (statsResult.status === 'fulfilled') setStats(statsResult.value);
        if (txsResult.status === 'fulfilled') setTransactions(txsResult.value.transactions ?? []);
        if (flaggedResult.status === 'fulfilled') setFlagged(flaggedResult.value.transactions ?? []);
        const failures = results.filter(result => result.status === 'rejected');
        setError(failures.length ? 'Some live data is temporarily unavailable. Showing the latest successful results.' : null);
        if (failures.length !== results.length) setLastUpdate(new Date());
      } catch {
        if (active) setError('Unable to refresh live data. Retrying automatically.');
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
    high: flagged.filter((tx) => tx.risk_score >= 40).length,
  }), [transactions, flagged]);

  useEffect(() => setPage(0), [filter, search, watchOnly]);

  const filtered = useMemo(() => {
    let list = transactions;

    // For flagged/high views, use the dedicated flagged list
    if (filter === 'flagged') list = flagged;
    else if (filter === 'high') list = flagged.filter((tx) => tx.risk_score >= 40);

    if (watchOnly) list = list.filter(tx => watchlist.includes(tx.from_address?.toLowerCase()) || watchlist.includes(tx.to_address?.toLowerCase()));

    if (search.trim()) {
      const s = search.toLowerCase();
      list = list.filter((tx) =>
        (tx.hash ?? '').toLowerCase().includes(s) ||
        (tx.from_address ?? '').toLowerCase().includes(s) ||
        (tx.to_address ?? '').toLowerCase().includes(s)
      );
    }

    return list;
  }, [transactions, flagged, filter, search, watchOnly, watchlist]);

  function toggleWatch(address) {
    if (!address) return;
    const normalized = address.toLowerCase();
    setWatchlist(previous => {
      const next = previous.includes(normalized) ? previous.filter(a => a !== normalized) : [...previous, normalized];
      localStorage.setItem('chainscope-watchlist', JSON.stringify(next));
      return next;
    });
  }

  async function inspectTransaction(tx) {
    setSelectedTx(tx);
    try {
      const details = await api.getTransaction(tx.hash);
      setSelectedTx(current => current?.hash === tx.hash ? details : current);
    } catch {
      // The selected transaction may have expired under retention.
    }
  }

  return (
    <div className="min-h-screen bg-[#070d1b] text-slate-100">
      <header className="border-b border-cyan-400/10 bg-[#0a1223]/95 mb-7">
        <div className="max-w-7xl mx-auto px-6 py-5 flex flex-wrap gap-4 items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-cyan-400/10 border border-cyan-400/30 flex items-center justify-center text-2xl">⬡</div>
            <div>
              <div className="text-[10px] tracking-[0.32em] text-cyan-400 font-bold uppercase">Ethereum threat intelligence</div>
              <h1 className="text-2xl font-extrabold text-white tracking-tight">CHAIN<span className="text-cyan-400">SCOPE</span> <span className="text-xs font-medium text-slate-500 align-middle">/ COMMAND CENTER</span></h1>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-xl bg-emerald-500/5 border border-emerald-400/20 px-4 py-2">
            <span className={`w-2.5 h-2.5 rounded-full ${error ? 'bg-rose-400' : 'bg-emerald-400 animate-pulse'}`} />
            <div><div className="text-xs font-semibold text-emerald-300">{error ? 'FEED INTERRUPTED' : 'LIVE DATA FEED'}</div><div className="text-[11px] text-slate-500">Last sync {lastUpdate.toLocaleTimeString()}</div></div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 pb-12">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">
            ⚠️ Error: {error}
          </div>
        )}

        <div className="mb-6">
          <div className="text-xs uppercase tracking-[0.25em] text-cyan-400 mb-2">Intelligence overview / Ethereum mainnet</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-white mb-2">Follow the money. <span className="text-cyan-400">Surface the signals.</span></h2>
          <p className="text-slate-400 text-sm">Live transaction monitoring, evidence-backed risk detection, and interactive wallet investigations.</p>
        </div>
        {loading && <p role="status" className="text-sm text-slate-400 mb-4">Connecting to Ethereum intelligence feed…</p>}
        <StatsBar stats={stats} />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 mt-6"><ActivityPanel transactions={transactions}/><div className="rounded-2xl border border-slate-700/70 bg-[#111e31] p-6"><div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-bold">Investigation tools</div><h3 className="text-lg font-semibold mt-1">Your analyst workspace</h3><p className="text-sm text-slate-400 mt-2">Save wallet addresses locally, filter observed activity and export evidence for review. Watchlists stay in this browser.</p><div className="mt-5 flex flex-wrap gap-2"><button onClick={() => setWatchOnly(v => !v)} className={`rounded-xl border px-4 py-2 text-sm ${watchOnly ? "bg-cyan-400 text-slate-950 border-cyan-400" : "border-slate-600 text-slate-200 hover:border-cyan-400"}`}>☆ Watchlist only ({watchlist.length})</button><button onClick={() => downloadTransactions(filtered)} className="rounded-xl border border-slate-600 px-4 py-2 text-sm hover:border-cyan-400">↓ Export {filtered.length} CSV rows</button></div></div></div>
        <div className="flex flex-wrap gap-2 my-7 border-b border-slate-700/60 pb-3">
          <button onClick={() => setView('investigate')} className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition ${view === 'investigate' ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>◎ Investigation graph</button>
          <button onClick={() => setView('transactions')} className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition ${view === 'transactions' ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>≡ Transaction explorer</button>
        </div>
        {view === 'investigate' && <div className="mb-7"><InvestigationGraph transactions={flagged} onSelect={inspectTransaction} /></div>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <div className="lg:col-span-2">
            <div className="flex gap-3 mb-4">
              <SearchBar value={search} onChange={setSearch} />
            </div>
            <FilterTabs active={filter} onChange={setFilter} counts={counts} />
          </div>
          <div className="lg:col-span-1">
            <RiskChart transactions={transactions} />
          </div>
        </div>

        <TransactionList transactions={filtered.slice(page * 20, (page + 1) * 20)} onSelect={inspectTransaction} />
        <div className="flex justify-between items-center mt-4 text-sm text-slate-400"><span>Showing {filtered.length ? page * 20 + 1 : 0}–{Math.min((page + 1) * 20, filtered.length)} of {filtered.length} loaded results</span><div className="flex gap-2"><button disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))} className="px-4 py-2 rounded-lg bg-slate-800 disabled:opacity-40">Previous</button><button disabled={(page + 1) * 20 >= filtered.length} onClick={() => setPage(p => p + 1)} className="px-4 py-2 rounded-lg bg-slate-800 disabled:opacity-40">Next</button></div></div>
      </main>

      <footer className="text-center text-slate-600 text-xs py-8">
        CHAINSCOPE · Ethereum intelligence · Risk indicators are not proof of wrongdoing
      </footer>

      {selectedTx && <div className="fixed bottom-5 left-5 z-[60] flex gap-2 rounded-xl border border-cyan-500/30 bg-slate-900 p-3 shadow-2xl"><button onClick={() => toggleWatch(selectedTx.from_address)} className="text-xs text-cyan-300 px-2 py-1">{watchlist.includes(selectedTx.from_address?.toLowerCase()) ? '★ Unwatch sender' : '☆ Watch sender'}</button><button onClick={() => toggleWatch(selectedTx.to_address)} className="text-xs text-cyan-300 px-2 py-1">{watchlist.includes(selectedTx.to_address?.toLowerCase()) ? '★ Unwatch recipient' : '☆ Watch recipient'}</button></div>}
      {selectedTx && (
        <TransactionModal tx={selectedTx} onClose={() => setSelectedTx(null)} />
      )}
    </div>
  );
}

export default App;