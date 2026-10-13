function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return '0.0000 ETH';
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0');
    return `${whole}.${fraction.slice(0, 4)} ETH`;
  }
  const value = Number(tx.value_eth);
  return Number.isFinite(value) ? `${value.toFixed(4)} ETH` : 'Amount unavailable';
}

function riskClasses(score) {
  if (score >= 80) return 'border-red-500/35 bg-red-500/10 text-red-400';
  if (score >= 40) return 'border-orange-500/35 bg-orange-500/10 text-orange-400';
  if (score >= 20) return 'border-yellow-500/35 bg-yellow-500/10 text-yellow-300';
  return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-400';
}

function short(value, head = 10, tail = 6) {
  if (!value) return 'N/A';
  return value.length <= head + tail + 3 ? value : `${value.slice(0, head)}...${value.slice(-tail)}`;
}

export default function TransactionList({ transactions, onSelect }) {
  return (
    <section className="transaction-panel">
      <div className="transaction-panel-head">
        <div><h2 className="text-lg font-semibold text-white">Transactions</h2><p className="mt-1 text-sm text-slate-400">{transactions?.length || 0} shown</p></div>
        <span className="text-xs text-slate-500">Click any row for details</span>
      </div>
      {!transactions?.length ? <div className="py-14 text-center text-sm text-slate-500">No transactions match your filters.</div> : (
        <div className="divide-y divide-[#39475d]">
          {transactions.map(tx => {
            const groundedAi = typeof tx.ai_explanation === 'string' && tx.ai_explanation.startsWith('Grounded AI explanation:');
            return <button key={tx.hash} onClick={() => onSelect(tx)} className="transaction-row">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-3"><span className="font-mono text-sm text-slate-300">{short(tx.hash)}</span><span className={`rounded border px-2 py-0.5 text-xs font-semibold ${riskClasses(Number(tx.risk_score) || 0)}`}>Risk: {Number(tx.risk_score) || 0}</span>{groundedAi && <span className="text-xs text-sky-400">Grounded AI</span>}</div>
                <div className="truncate font-mono text-xs text-slate-400">{short(tx.from_address)} → {short(tx.to_address)}</div>
              </div>
              <div className="ml-5 shrink-0 text-right"><div className="text-lg font-semibold text-white">{formatEth(tx)}</div><div className="mt-1 text-xs text-slate-500">Block {Number(tx.block_number || 0).toLocaleString()}</div></div>
            </button>;
          })}
        </div>
      )}
    </section>
  );
}
