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

function App() {
  const [stats, setStats] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [flagged, setFlagged] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());
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

  const filtered = useMemo(() => {
    let list = transactions;

    // For flagged/high views, use the dedicated flagged list
    if (filter === 'flagged') list = flagged;
    else if (filter === 'high') list = flagged.filter((tx) => tx.risk_score >= 40);

    if (search.trim()) {
      const s = search.toLowerCase();
      list = list.filter((tx) =>
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

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <header className="border-b border-slate-700 bg-slate-800/95 mb-7">
        <div className="max-w-7xl mx-auto px-6 py-5 flex flex-wrap gap-4 items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">🔗 Blockchain Intelligence Platform</h1>
            <p className="text-sm text-slate-400 mt-1">AI-powered Ethereum transaction analysis</p>
          </div>
          <div className="text-sm">
            <div className={error ? 'text-rose-400' : 'text-emerald-400'}>● {error ? 'Feed unavailable' : 'Live'}</div>
            <div className="text-xs text-slate-500 mt-1">Updated: {lastUpdate.toLocaleTimeString()}</div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 pb-12">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400">
            ⚠️ Error: {error}
          </div>
        )}

        {loading && <p role="status" className="text-sm text-slate-400 mb-4">Connecting to Ethereum intelligence feed…</p>}
        <StatsBar stats={stats} />
        <nav aria-label="Dashboard sections" className="flex flex-wrap gap-2 mt-5 mb-6">
          <button onClick={() => setView('transactions')} className={`rounded-lg px-4 py-2 text-sm transition ${view === 'transactions' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>Transactions</button>
          <button onClick={() => setView('wallet')} className={`rounded-lg px-4 py-2 text-sm transition ${view === 'wallet' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>Wallet lookup</button>
          <button onClick={() => setView('investigate')} className={`rounded-lg px-4 py-2 text-sm transition ${view === 'investigate' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>Investigation graph</button>
        </nav>
        {view === 'wallet' && <div className="mb-7"><WalletInvestigator /></div>}
        {view === 'investigate' && <div className="mb-7"><WalletGraphWorkspace flagged={flagged} onSelect={inspectTransaction} /></div>}
        {view === 'transactions' && <>

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

        <TransactionList transactions={filtered} onSelect={inspectTransaction} />
        </>}
      </main>

      <footer className="text-center text-slate-600 text-xs py-8">
        CHAINSCOPE · Ethereum intelligence · Risk indicators are not proof of wrongdoing
      </footer>

      {selectedTx && (
        <TransactionModal tx={selectedTx} onClose={() => setSelectedTx(null)} />
      )}
    </div>
  );
}

export default App;