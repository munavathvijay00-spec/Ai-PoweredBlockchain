import { useMemo, useState } from 'react';

const short = (value) => value ? `${value.slice(0, 10)}...${value.slice(-6)}` : 'Unknown';
const riskStyle = (score) => score >= 80 ? 'text-red-400' : score >= 40 ? 'text-orange-400' : score >= 20 ? 'text-yellow-400' : 'text-emerald-400';

export default function InvestigationGraph({ transactions = [], onSelect }) {
  const [query, setQuery] = useState('');
  const [selectedAddress, setSelectedAddress] = useState(null);

  const { transfers, walletCount } = useMemo(() => {
    const transfers = transactions.filter(tx => tx.from_address && tx.to_address);
    const addresses = new Set(transfers.flatMap(tx => [tx.from_address.toLowerCase(), tx.to_address.toLowerCase()]));
    return { transfers, walletCount: addresses.size };
  }, [transactions]);

  const visible = useMemo(() => transfers.filter(tx => {
    const matchesQuery = !query.trim() || [tx.hash, tx.from_address, tx.to_address]
      .some(value => (value || '').toLowerCase().includes(query.trim().toLowerCase()));
    const matchesWallet = !selectedAddress ||
      tx.from_address.toLowerCase() === selectedAddress ||
      tx.to_address.toLowerCase() === selectedAddress;
    return matchesQuery && matchesWallet;
  }), [transfers, query, selectedAddress]);

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-800 overflow-hidden">
      <div className="px-6 py-5 border-b border-slate-700 flex flex-wrap justify-between items-start gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Wallet connections</h2>
          <p className="text-sm text-slate-400 mt-1">Observed sender and recipient relationships in the current flagged transaction sample.</p>
        </div>
        <div className="text-sm text-slate-400">{walletCount} wallets · {transfers.length} transfers</div>
      </div>
      <div className="px-6 py-4 border-b border-slate-700 flex flex-wrap gap-3 items-center">
        <input
          aria-label="Search wallet connections"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Search wallet or transaction hash..."
          className="flex-1 min-w-[210px] rounded-lg bg-slate-900 border border-slate-600 px-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-slate-400"
        />
        {selectedAddress && (
          <button onClick={() => setSelectedAddress(null)} className="text-sm text-slate-300 hover:text-white border border-slate-600 rounded-lg px-3 py-2.5">
            Clear wallet filter ×
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400 bg-slate-900/40">
            <tr><th className="px-6 py-3 font-medium">From wallet</th><th className="px-6 py-3 font-medium">To wallet</th><th className="px-6 py-3 font-medium">Risk indicator</th><th className="px-6 py-3 font-medium">Transaction</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-700">
            {visible.map((tx, index) => (
              <tr key={tx.hash + '-' + index} className="hover:bg-slate-700/40">
                <td className="px-6 py-3"><button title={tx.from_address} onClick={() => setSelectedAddress(tx.from_address.toLowerCase())} className="font-mono text-slate-200 hover:text-blue-400">{short(tx.from_address)}</button></td>
                <td className="px-6 py-3"><button title={tx.to_address} onClick={() => setSelectedAddress(tx.to_address.toLowerCase())} className="font-mono text-slate-200 hover:text-blue-400">{short(tx.to_address)}</button></td>
                <td className={`px-6 py-3 font-semibold ${riskStyle(Number(tx.risk_score) || 0)}`}>{tx.risk_score == null ? 'Not assessed' : tx.risk_score}</td>
                <td className="px-6 py-3"><button onClick={() => onSelect(tx)} className="text-blue-400 hover:text-blue-300 font-mono" title={tx.hash}>{short(tx.hash)} ↗</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && <p className="px-6 py-10 text-center text-sm text-slate-400">No matching connections in the current sample.</p>}
      </div>
      <p className="px-6 py-4 border-t border-slate-700 text-xs text-slate-500">
        Only relationships in the loaded flagged transaction sample are shown. A transfer does not establish shared ownership or wrongdoing.
      </p>
    </section>
  );
}
