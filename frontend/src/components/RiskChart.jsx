import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

function categorize(transactions) {
  const buckets = { minimal: 0, low: 0, medium: 0, high: 0 };
  transactions.forEach(tx => {
    const score = Number(tx.risk_score) || 0;
    if (score >= 80) buckets.high += 1;
    else if (score >= 40) buckets.medium += 1;
    else if (score >= 20) buckets.low += 1;
    else buckets.minimal += 1;
  });
  return [
    { name: 'Minimal', range: '0–19', value: buckets.minimal, color: '#22c55e' },
    { name: 'Low', range: '20–39', value: buckets.low, color: '#eab308' },
    { name: 'Medium', range: '40–79', value: buckets.medium, color: '#f97316' },
    { name: 'High', range: '80–100', value: buckets.high, color: '#ef4444' },
  ].filter(item => item.value > 0);
}

export default function RiskChart({ transactions = [] }) {
  const data = categorize(transactions);
  const total = transactions.length;
  return (
    <section className="platform-card h-full min-h-[274px] p-6">
      <h2 className="text-base font-semibold text-white">Risk Distribution</h2>
      {!total ? <div className="grid h-[190px] place-items-center text-sm text-slate-500">Waiting for transaction data…</div> : (
        <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row">
          <div className="h-40 w-40 shrink-0">
            <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} cx="50%" cy="50%" innerRadius={47} outerRadius={74} paddingAngle={1} dataKey="value" stroke="#d8e2f0" strokeWidth={1}>{data.map(item => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ backgroundColor: '#202c40', border: '1px solid #425168', borderRadius: '8px', color: '#f1f5f9' }} /></PieChart></ResponsiveContainer>
          </div>
          <div className="w-full min-w-0 space-y-3">
            {data.map(item => <div key={item.name} className="grid grid-cols-[1fr_auto] gap-4 text-sm"><div className="flex min-w-0 items-center gap-2"><span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: item.color }} /><span className="text-slate-300">{item.name}<span className="block text-xs text-slate-400">({item.range})</span></span></div><span className="whitespace-nowrap font-mono text-slate-400">{item.value}<span className="block text-xs">({((item.value / total) * 100).toFixed(1)}%)</span></span></div>)}
          </div>
        </div>
      )}
    </section>
  );
}
