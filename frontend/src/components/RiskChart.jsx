import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

export default function RiskChart({ distribution, asOf }) {
  if (distribution == null) {
    return <section className="platform-card h-full min-h-[274px] p-6" aria-labelledby="risk-distribution-title" aria-busy="true">
      <h2 id="risk-distribution-title" className="text-base font-semibold text-white">Risk Distribution</h2>
      <div className="mt-5 flex items-center gap-5" role="status" aria-live="polite">
        <div className="h-40 w-40 shrink-0 animate-pulse rounded-full bg-slate-800/80" />
        <div className="w-full space-y-3">{[0, 1, 2, 3].map(i => <div key={i} className="h-8 animate-pulse rounded bg-slate-800/70" />)}</div>
        <span className="sr-only">Loading risk distribution</span>
      </div>
    </section>;
  }

  const total = Number(distribution?.population || 0);
  const data = [
    { name: 'Minimal', range: '0–19', value: Number(distribution?.minimal || 0), color: '#22c55e', symbol: '○' },
    { name: 'Review', range: '20–39', value: Number(distribution?.review || 0), color: '#eab308', symbol: '◆' },
    { name: 'High review', range: '40–79', value: Number(distribution?.high_review || 0), color: '#f97316', symbol: '▲' },
    { name: 'Critical', range: '80–100', value: Number(distribution?.critical || 0), color: '#ef4444', symbol: '●' },
  ];
  const pieData = data.filter(item => item.value > 0);
  const flagged = data.slice(1).reduce((sum, item) => sum + item.value, 0);
  const textualSummary = total
    ? data.map(item => `${item.name} ${item.value} (${((item.value / total) * 100).toFixed(1)}%)`).join(', ')
    : 'No matching transactions.';

  return <section className="platform-card h-full min-h-[274px] p-6" aria-labelledby="risk-distribution-title">
    <div className="flex items-start justify-between gap-4">
      <div><h2 id="risk-distribution-title" className="text-base font-semibold text-white">Risk Distribution</h2><p className="mt-1 text-xs text-slate-400">All {total.toLocaleString()} retained transactions matching the current filters</p><p className="mt-1 text-[11px] text-slate-500">As of {asOf ? asOf.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'latest refresh'} · Flagged = risk ≥20</p></div>
      <span className="rounded border border-emerald-400/30 bg-emerald-400/[0.08] px-2 py-1 text-[10px] uppercase tracking-wide text-emerald-200">full population</span>
    </div>
    <p className="sr-only">{textualSummary}. Flagged total {flagged}.</p>
    {!total ? <div className="grid h-[190px] place-items-center text-center text-sm text-slate-400"><span>No transactions match the active filters.<br /><span className="text-xs text-slate-500">Clear or broaden filters to restore the distribution.</span></span></div> : <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row">
      <div className="h-40 w-40 shrink-0" aria-hidden="true"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={pieData} cx="50%" cy="50%" innerRadius={47} outerRadius={74} paddingAngle={1} dataKey="value" stroke="#d8e2f0" strokeWidth={1}>{pieData.map(item => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ backgroundColor: '#202c40', border: '1px solid #64748b', borderRadius: '8px', color: '#f8fafc' }} /></PieChart></ResponsiveContainer></div>
      <div className="w-full min-w-0 space-y-3">{data.map(item => <div key={item.name} className="grid grid-cols-[1fr_auto] gap-4 text-sm"><div className="flex min-w-0 items-center gap-2"><span className="w-4 shrink-0 text-center font-bold text-slate-100" aria-hidden="true">{item.symbol}</span><span className="text-slate-200">{item.name}<span className="block text-xs text-slate-400">Risk {item.range}</span></span></div><span className="whitespace-nowrap font-mono text-slate-300">{item.value.toLocaleString()}<span className="block text-xs text-slate-400">({total ? ((item.value / total) * 100).toFixed(1) : '0.0'}%)</span></span></div>)}<div className="border-t border-[#46566f] pt-2 text-xs text-slate-400">Flagged total: <span className="font-semibold text-slate-100">{flagged.toLocaleString()}</span></div></div>
    </div>}
  </section>;
}
