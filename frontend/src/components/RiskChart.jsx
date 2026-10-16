import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

export default function RiskChart({ distribution }) {
  const total = Number(distribution?.population || 0);
  const data = [
    { name: 'Minimal', range: '0–19', value: Number(distribution?.minimal || 0), color: '#22c55e' },
    { name: 'Review', range: '20–39', value: Number(distribution?.review || 0), color: '#eab308' },
    { name: 'High review', range: '40–79', value: Number(distribution?.high_review || 0), color: '#f97316' },
    { name: 'Critical review', range: '80–100', value: Number(distribution?.critical || 0), color: '#ef4444' },
  ].filter(item => item.value > 0);

  const textualSummary = total
    ? data.map(item => `${item.name} ${item.value} (${((item.value / total) * 100).toFixed(1)}%)`).join(', ')
    : 'No matching transactions.';

  return (
    <section className="platform-card h-full min-h-[274px] p-6" aria-labelledby="risk-distribution-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="risk-distribution-title" className="text-base font-semibold text-white">Risk Distribution</h2>
          <p className="mt-1 text-xs text-slate-500">All {total.toLocaleString()} retained transactions matching the current filters</p>
        </div>
        <span className="rounded border border-emerald-400/20 bg-emerald-400/[0.06] px-2 py-1 text-[10px] uppercase tracking-wide text-emerald-300">full population</span>
      </div>
      <p className="sr-only">{textualSummary}</p>
      {!total ? <div className="grid h-[190px] place-items-center text-sm text-slate-500">No matching transactions to chart.</div> : (
        <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row">
          <div className="h-40 w-40 shrink-0" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} cx="50%" cy="50%" innerRadius={47} outerRadius={74} paddingAngle={1} dataKey="value" stroke="#d8e2f0" strokeWidth={1}>{data.map(item => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ backgroundColor: '#202c40', border: '1px solid #425168', borderRadius: '8px', color: '#f1f5f9' }} /></PieChart></ResponsiveContainer>
          </div>
          <div className="w-full min-w-0 space-y-3">
            {data.map(item => <div key={item.name} className="grid grid-cols-[1fr_auto] gap-4 text-sm"><div className="flex min-w-0 items-center gap-2"><span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: item.color }} aria-hidden="true" /><span className="text-slate-300">{item.name}<span className="block text-xs text-slate-400">Risk {item.range}</span></span></div><span className="whitespace-nowrap font-mono text-slate-400">{item.value.toLocaleString()}<span className="block text-xs">({((item.value / total) * 100).toFixed(1)}%)</span></span></div>)}
          </div>
        </div>
      )}
    </section>
  );
}
