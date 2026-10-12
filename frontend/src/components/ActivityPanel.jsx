import { useMemo } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function ActivityPanel({ transactions = [] }) {
  const data = useMemo(() => {
    const blocks = new Map();
    for (const tx of transactions) {
      const key = tx.block_number;
      if (!Number.isFinite(Number(key))) continue;
      const row = blocks.get(key) || { block: Number(key), total: 0, flagged: 0 };
      row.total++;
      if (tx.risk_score >= 20) row.flagged++;
      blocks.set(key, row);
    }
    return [...blocks.values()].sort((a, b) => a.block - b.block).slice(-24);
  }, [transactions]);

  return (
    <section className="rounded-2xl border border-slate-700/70 bg-[#111e31] p-5 shadow-xl shadow-black/10">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-5">
        <div><div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-bold">Network pulse</div><h3 className="text-lg font-semibold text-white mt-1">Recent block activity</h3></div>
        <span className="text-xs text-slate-400">Sample of {transactions.length} loaded transactions</span>
      </div>
      {data.length > 1 ? (
        <div className="h-48" role="img" aria-label="Transaction counts and flagged counts across recently loaded blocks">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs><linearGradient id="pulseFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35}/><stop offset="100%" stopColor="#22d3ee" stopOpacity={0}/></linearGradient></defs>
              <CartesianGrid stroke="#334155" strokeDasharray="3 5" vertical={false} />
              <XAxis dataKey="block" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={n => String(n).slice(-4)} />
              <YAxis allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 11 }} width={32}/>
              <Tooltip contentStyle={{ background: '#111e31', border: '1px solid #334155', borderRadius: 12 }} labelFormatter={n => 'Block ' + Number(n).toLocaleString()}/>
              <Area type="monotone" dataKey="total" name="Observed" stroke="#22d3ee" strokeWidth={2} fill="url(#pulseFill)" />
              <Area type="monotone" dataKey="flagged" name="Flagged" stroke="#fb923c" strokeWidth={2} fill="transparent" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : <p className="text-slate-400 text-sm py-10">Waiting for enough recent blocks to plot activity.</p>}
      <p className="text-xs text-slate-500 mt-3">This chart reflects the loaded sample, not network-wide totals.</p>
    </section>
  );
}
