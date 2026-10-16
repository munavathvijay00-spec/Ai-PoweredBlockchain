function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0');
    return `${whole}.${fraction.slice(0, 4)} ETH`;
  }
  const value = Number(tx.value_eth);
  return Number.isFinite(value) ? `${value.toFixed(4)} ETH` : 'Amount unavailable';
}

function riskMeta(score) {
  if (score >= 80) return { label: 'Critical review', cls: 'border-red-500/35 bg-red-500/10 text-red-400' };
  if (score >= 40) return { label: 'High review', cls: 'border-orange-500/35 bg-orange-500/10 text-orange-400' };
  if (score >= 20) return { label: 'Review', cls: 'border-yellow-500/35 bg-yellow-500/10 text-yellow-300' };
  return { label: 'Minimal', cls: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-400' };
}

function short(value, head = 8, tail = 6) {
  if (!value) return 'N/A';
  return value.length <= head + tail + 3 ? value : `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function timeLabel(timestamp) {
  if (!timestamp) return 'Unknown time';
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? 'Unknown time' : date.toLocaleString();
}

export default function TransactionList({ transactions = [], onSelect, totalMatches = 0, loading = false, error = null, onRetry }) {
  const shown = transactions.length;
  const total = Number(totalMatches || 0);

  return (
    <section className="transaction-panel" aria-labelledby="transactions-heading">
      <div className="transaction-panel-head">
        <div>
          <h2 id="transactions-heading" className="text-lg font-semibold text-white">Transactions</h2>
          <p className="mt-1 text-sm text-slate-400">{shown.toLocaleString()} shown on this page · {total.toLocaleString()} matching retained records</p>
        </div>
        <span className="text-xs text-slate-500">Use “View details” for evidence, factors, and attribution context.</span>
      </div>

      {loading && <div className="py-14 text-center text-sm text-slate-400" role="status">Loading transaction page…</div>}
      {!loading && error && <div className="py-14 text-center"><p className="text-sm text-rose-300">{error}</p>{onRetry && <button type="button" onClick={onRetry} className="workspace-chip mt-4">Retry</button>}</div>}
      {!loading && !error && !shown && <div className="py-14 text-center text-sm text-slate-500">No transactions match the current filters. Reset filters or broaden the selected ranges.</div>}

      {!loading && !error && shown > 0 && <>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full border-collapse text-left text-sm">
            <caption className="sr-only">Ethereum transactions matching the current filters</caption>
            <thead className="border-y border-[#39475d] bg-[#111d31] text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3">Time</th><th scope="col" className="px-4 py-3">Hash</th>
                <th scope="col" className="px-4 py-3">From</th><th scope="col" className="px-4 py-3">To</th>
                <th scope="col" className="px-4 py-3">Value</th><th scope="col" className="px-4 py-3">Risk</th>
                <th scope="col" className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#39475d]">
              {transactions.map(tx => {
                const risk = riskMeta(Number(tx.risk_score) || 0);
                return <tr key={tx.hash} className="hover:bg-white/[0.025] focus-within:bg-white/[0.035]">
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{timeLabel(tx.timestamp)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300" title={tx.hash}>{short(tx.hash)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400" title={tx.from_address}>{short(tx.from_address)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400" title={tx.to_address}>{short(tx.to_address)}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-white">{formatEth(tx)}</td>
                  <td className="px-4 py-3"><span className={`inline-flex rounded border px-2 py-1 text-xs font-semibold ${risk.cls}`}>{risk.label} · {Number(tx.risk_score) || 0}</span></td>
                  <td className="px-4 py-3"><button type="button" onClick={() => onSelect(tx)} className="workspace-chip" aria-label={`View details for transaction ${tx.hash}`}>View details</button></td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>

        <div className="divide-y divide-[#39475d] md:hidden">
          {transactions.map(tx => {
            const risk = riskMeta(Number(tx.risk_score) || 0);
            return <article key={tx.hash} className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3"><div><p className="font-mono text-sm text-slate-200">{short(tx.hash, 10, 8)}</p><p className="mt-1 text-xs text-slate-500">{timeLabel(tx.timestamp)}</p></div><span className={`rounded border px-2 py-1 text-[11px] font-semibold ${risk.cls}`}>{risk.label} · {Number(tx.risk_score) || 0}</span></div>
              <dl className="grid grid-cols-[60px_1fr] gap-x-2 gap-y-1 text-xs"><dt className="text-slate-500">From</dt><dd className="truncate font-mono text-slate-300">{tx.from_address}</dd><dt className="text-slate-500">To</dt><dd className="truncate font-mono text-slate-300">{tx.to_address}</dd><dt className="text-slate-500">Value</dt><dd className="text-white">{formatEth(tx)}</dd><dt className="text-slate-500">Block</dt><dd className="text-slate-300">{Number(tx.block_number || 0).toLocaleString()}</dd></dl>
              <button type="button" onClick={() => onSelect(tx)} className="workspace-chip w-full" aria-label={`View details for transaction ${tx.hash}`}>View details</button>
            </article>;
          })}
        </div>
      </>}
    </section>
  );
}
