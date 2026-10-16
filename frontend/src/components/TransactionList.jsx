import { bestAddressLabel } from '../utils/knownContracts';

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return { text: '—', title: '0 ETH' };
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    const text = `${whole}${fraction ? `.${fraction.slice(0, 6)}` : ''} ETH`;
    return { text, title: text };
  }
  const value = Number(tx.value_eth);
  if (!Number.isFinite(value)) return { text: '—', title: 'Amount unavailable' };
  if (value === 0) return { text: '—', title: '0 ETH' };
  const text = `${value.toPrecision(6)} ETH`;
  return { text, title: text };
}

function riskMeta(score) {
  if (score >= 80) return { label: 'Critical', cls: 'border-red-500/35 bg-red-500/10 text-red-300', symbol: '●' };
  if (score >= 40) return { label: 'High review', cls: 'border-orange-500/35 bg-orange-500/10 text-orange-300', symbol: '▲' };
  if (score >= 20) return { label: 'Review', cls: 'border-yellow-500/35 bg-yellow-500/10 text-yellow-200', symbol: '◆' };
  if (score > 0) return { label: 'Low signal', cls: 'border-emerald-500/25 bg-emerald-500/[0.07] text-emerald-300', symbol: '○' };
  return { label: 'No signal', cls: 'border-slate-600 bg-slate-800/50 text-slate-400', symbol: '—' };
}

function shortHash(value) {
  if (!value) return 'N/A';
  return value.length <= 21 ? value : `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function shortAddress(value) {
  if (!value) return 'N/A';
  return value.length <= 17 ? value : `${value.slice(0, 8)}…${value.slice(-6)}`;
}

function parseUtc(timestamp) {
  if (!timestamp) return null;
  const raw = String(timestamp);
  const explicit = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(explicit);
  return Number.isNaN(date.getTime()) ? null : date;
}

function timeLabel(timestamp) {
  const date = parseUtc(timestamp);
  if (!date) return 'Unknown time';
  return `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

function factorReason(tx) {
  const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors : [];
  const first = factors.find(item => item && typeof item === 'object');
  return first?.reason || first?.name || first?.type || null;
}

function AddressCell({ address, matches = [] }) {
  const label = bestAddressLabel(address, matches);
  return <div className="min-w-0"><div className="font-mono text-xs text-slate-300" title={address}>{shortAddress(address)}</div>{label && <div className="mt-1 max-w-[180px] truncate text-[10px] font-medium text-sky-300" title={`${label.label} · ${label.type}`}>{label.label} · {label.type}</div>}</div>;
}

function SortHeader({ label, field, sort, onSort, className = '' }) {
  const desc = `${field}_desc`;
  const asc = `${field}_asc`;
  const active = sort === desc || sort === asc;
  const next = sort === desc ? asc : desc;
  return <th scope="col" className={`px-4 py-3 ${className}`}><button type="button" onClick={() => onSort(next)} className="inline-flex items-center gap-1 hover:text-sky-300">{label}<span aria-hidden="true">{active ? (sort === desc ? '↓' : '↑') : '↕'}</span></button></th>;
}

export default function TransactionList({ transactions = [], onSelect, totalMatches = 0, loading = false, error = null, onRetry, offset = 0, sort = 'risk_desc', onSort = () => {} }) {
  const shown = transactions.length;
  const total = Number(totalMatches || 0);
  const start = shown ? Number(offset) + 1 : 0;
  const end = shown ? Number(offset) + shown : 0;

  return <section className="transaction-panel" aria-labelledby="transactions-heading">
    <div className="transaction-panel-head"><div><h2 id="transactions-heading" className="text-lg font-semibold text-white">Transactions</h2><p className="mt-1 text-sm text-slate-400">Showing {start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()} matching records</p></div><span className="text-xs text-slate-500">Simple review · open only when needed</span></div>

    {loading && <div className="space-y-3 p-6">{[0,1,2,3].map(i => <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-800/70" />)}</div>}
    {!loading && error && <div className="py-14 text-center"><p className="text-sm text-rose-300">{error}</p>{onRetry && <button type="button" onClick={onRetry} className="workspace-chip mt-4">Retry</button>}</div>}
    {!loading && !error && !shown && <div className="py-14 text-center text-sm text-slate-500">No transactions match the current filters.</div>}

    {!loading && !error && shown > 0 && <>
      <div className="hidden overflow-x-auto md:block"><table className="w-full border-collapse text-left text-sm"><thead className="border-y border-[#39475d] bg-[#111d31] text-xs uppercase tracking-wide text-slate-500"><tr><SortHeader label="Time" field="time" sort={sort === 'newest' ? 'time_desc' : sort === 'oldest' ? 'time_asc' : sort} onSort={value => onSort(value === 'time_desc' ? 'newest' : 'oldest')} /><th className="px-4 py-3">Hash</th><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><SortHeader label="Value" field="value" sort={sort} onSort={onSort} /><SortHeader label="Risk" field="risk" sort={sort} onSort={onSort} /><th className="px-4 py-3">Signal</th><th className="px-4 py-3">Action</th></tr></thead><tbody className="divide-y divide-[#39475d]">{transactions.map(tx => {
        const score = Number(tx.risk_score) || 0;
        const risk = riskMeta(score);
        const amount = formatEth(tx);
        const reason = factorReason(tx);
        return <tr key={tx.hash} className="hover:bg-white/[0.025]"><td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{timeLabel(tx.timestamp)}</td><td className="px-4 py-3 font-mono text-xs text-slate-300" title={tx.hash}>{shortHash(tx.hash)}</td><td className="px-4 py-3"><AddressCell address={tx.from_address} matches={tx.entity_context?.sender} /></td><td className="px-4 py-3"><AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} /></td><td className="whitespace-nowrap px-4 py-3 font-medium text-white">{amount.text}</td><td className="px-4 py-3"><span className={`inline-flex rounded border px-2 py-1 text-xs font-semibold ${risk.cls}`}>{risk.symbol} {risk.label}{score ? ` · ${score}` : ''}</span></td><td className="max-w-[240px] px-4 py-3 text-xs text-slate-400">{reason || 'No recorded signal'}</td><td className="px-4 py-3"><button type="button" onClick={() => onSelect(tx)} className="workspace-chip">View details</button></td></tr>;
      })}</tbody></table></div>

      <div className="divide-y divide-[#39475d] md:hidden">{transactions.map(tx => {
        const score = Number(tx.risk_score) || 0;
        const risk = riskMeta(score);
        const amount = formatEth(tx);
        return <article key={tx.hash} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-mono text-sm text-slate-200">{shortHash(tx.hash)}</p><p className="mt-1 text-xs text-slate-500">{timeLabel(tx.timestamp)}</p></div><span className={`rounded border px-2 py-1 text-[11px] ${risk.cls}`}>{risk.label}{score ? ` · ${score}` : ''}</span></div><div className="grid grid-cols-[56px_1fr] gap-2 text-xs"><span className="text-slate-500">From</span><AddressCell address={tx.from_address} matches={tx.entity_context?.sender} /><span className="text-slate-500">To</span><AddressCell address={tx.to_address} matches={tx.entity_context?.recipient} /><span className="text-slate-500">Value</span><span className="text-white">{amount.text}</span></div><button type="button" onClick={() => onSelect(tx)} className="workspace-chip w-full">View details</button></article>;
      })}</div>
    </>}
  </section>;
}
