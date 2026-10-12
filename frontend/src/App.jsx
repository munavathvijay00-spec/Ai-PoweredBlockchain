import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import StatsBar from './components/StatsBar';
import TransactionList from './components/TransactionList';
import TransactionModal from './components/TransactionModal';
import SearchBar from './components/SearchBar';
import FilterTabs from './components/FilterTabs';
import RiskChart from './components/RiskChart';
import InvestigationGraph from './components/InvestigationGraph';

function App() {
  const [stats, setStats] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [flagged, setFlagged] = useState([]);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [selectedTx, setSelectedTx] = useState(null);
  const [view, setView] = useState('investigate');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  async function loadData() {
    try {
      const [statsData, txsData, flaggedData] = await Promise.all([
        api.getStats(),
        api.getTransactions(50),
        api.getFlagged(20),
      ]);
      setStats(statsData);
      setTransactions(txsData.transactions);
      setFlagged(flaggedData.transactions);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
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
        tx.hash.toLowerCase().includes(s) ||
        tx.from_address.toLowerCase().includes(s) ||
        tx.to_address.toLowerCase().includes(s)
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
        <StatsBar stats={stats} />
        <div className="flex gap-2 my-7 border-b border-slate-700/60 pb-3">
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

        <TransactionList transactions={filtered} onSelect={inspectTransaction} />
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