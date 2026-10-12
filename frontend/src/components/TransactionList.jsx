function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return '0 ETH';
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    return String(whole) + (fraction ? '.' + fraction : '') + ' ETH';
  }
  const value = Number(tx.value_eth);
  if (!Number.isFinite(value)) return 'Amount unavailable';
  return value === 0 ? '0 ETH' : value.toPrecision(6) + ' ETH';
}

import { classifyTransaction } from '../utils/investigation';

/**
 * List of recent transactions with risk color coding.
 */

function riskColor(score) {
  if (score >= 80) return 'text-red-500 bg-red-500/10 border-red-500/30';
  if (score >= 40) return 'text-orange-500 bg-orange-500/10 border-orange-500/30';
  if (score >= 20) return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30';
  return 'text-green-500 bg-green-500/10 border-green-500/30';
}

function shortHash(hash) {
  if (!hash) return 'N/A';
  return `${hash.slice(0, 10)}...${hash.slice(-6)}`;
}

export default function TransactionList({ transactions, onSelect }) {
  if (!transactions || transactions.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <div className="text-slate-400 text-center py-8">No transactions match your filters.</div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Transactions</h2>
          <p className="text-slate-400 text-sm mt-1">{transactions.length} shown</p>
        </div>
        <span className="text-slate-500 text-xs">Click any row for details</span>
      </div>
      <div className="divide-y divide-slate-700">
        {transactions.map((tx) => (
          <button
            key={tx.hash}
            onClick={() => onSelect(tx)}
            className="w-full text-left px-6 py-4 hover:bg-slate-700/50 transition-colors cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-sm font-mono text-slate-300">{shortHash(tx.hash)}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${riskColor(tx.risk_score)}`}>
                    Risk: {tx.risk_score}
                  </span>
                  <span className={`text-[10px] border px-2 py-0.5 rounded-full ${classifyTransaction(tx).tone}`} title={classifyTransaction(tx).hint}>{classifyTransaction(tx).label}</span>
                  {tx.ai_explanation && (
                    <span className="text-xs text-blue-400">🧠 AI analyzed</span>
                  )}
                </div>
                <div className="text-xs text-slate-400 font-mono truncate">
                  {shortHash(tx.from_address)} → {shortHash(tx.to_address)}
                </div>
              </div>
              <div className="text-right ml-4">
                <div className="text-lg font-semibold text-white">
                  {formatEth(tx)}
                </div>
                <div className="text-xs text-slate-500">
                  {String(tx.value_wei) === '0' ? 'No native ETH · ' : ''}Block {tx.block_number.toLocaleString()}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}