import { useMemo, useState } from 'react';

const short = (s) => s ? `${s.slice(0, 7)}…${s.slice(-4)}` : 'Unknown';
const tone = (score) => score >= 80 ? '#fb7185' : score >= 40 ? '#fb923c' : score >= 20 ? '#facc15' : '#38bdf8';

export default function InvestigationGraph({ transactions, onSelect }) {
  const [focus, setFocus] = useState(null);
  const { nodes, edges } = useMemo(() => {
    const links = (transactions || []).filter(t => t.from_address && t.to_address).slice(0, 28);
    const counts = new Map();
    for (const t of links) {
      for (const address of [t.from_address, t.to_address]) {
        const prev = counts.get(address) || { address, score: 0, count: 0 };
        counts.set(address, { ...prev, score: Math.max(prev.score, t.risk_score), count: prev.count + 1 });
      }
    }
    const sorted = [...counts.values()].sort((a, b) => b.score - a.score || b.count - a.count).slice(0, 34);
    const ids = new Set(sorted.map(n => n.address));
    const plotted = sorted.map((n, i) => {
      const angle = i * 2.399963229728653;
      const radius = 54 + Math.sqrt(i / Math.max(sorted.length, 1)) * 205;
      return { ...n, x: 360 + Math.cos(angle) * radius, y: 235 + Math.sin(angle) * radius };
    });
    const positions = new Map(plotted.map(n => [n.address, n]));
    return { nodes: plotted, edges: links.filter(t => ids.has(t.from_address) && ids.has(t.to_address)).map(t => ({
      ...t, source: positions.get(t.from_address), target: positions.get(t.to_address),
    })) };
  }, [transactions]);

  const active = focus ? edges.filter(e => e.from_address === focus || e.to_address === focus) : edges;
  return (
    <section className="rounded-2xl border border-cyan-400/20 bg-[#0c172b] overflow-hidden shadow-2xl shadow-cyan-950/20">
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 pt-5 pb-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] font-semibold text-cyan-400">Live investigation canvas</div>
          <h2 className="text-xl font-bold text-white mt-1">Threat relationship map</h2>
          <p className="text-xs text-slate-400 mt-1">Observed sender → recipient links from recent flagged transactions. Select a node or connection.</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span>{nodes.length} wallets</span><span className="text-slate-600">/</span><span>{edges.length} transfers</span>
          {focus && <button className="rounded-lg border border-cyan-500/30 px-3 py-1.5 text-cyan-300 hover:bg-cyan-500/10" onClick={() => setFocus(null)}>Clear focus ×</button>}
        </div>
      </div>
      <div className="relative mx-3 mb-3 rounded-xl border border-white/5 bg-[#080f20]" style={{ backgroundImage: 'radial-gradient(circle, #1d3551 1px, transparent 1px)', backgroundSize: '24px 24px' }}>
        {edges.length ? <svg viewBox="0 0 720 470" className="w-full h-auto min-h-[280px]" role="img" aria-label="Network of observed flagged Ethereum transfers">
          <defs><marker id="network-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="#64748b" /></marker></defs>
          {edges.map((e, i) => <line key={e.hash + i} x1={e.source.x} y1={e.source.y} x2={e.target.x} y2={e.target.y} stroke={tone(e.risk_score)} strokeWidth={focus ? (active.includes(e) ? 2.2 : .35) : 1.5} strokeOpacity={focus ? (active.includes(e) ? .85 : .08) : .5} markerEnd="url(#network-arrow)" onClick={() => onSelect(e)} className="cursor-pointer"><title>{short(e.hash)} · Risk {e.risk_score}</title></line>)}
          {nodes.map(n => <g key={n.address} onClick={() => setFocus(focus === n.address ? null : n.address)} className="cursor-pointer" opacity={focus && focus !== n.address && !active.some(e => e.from_address === n.address || e.to_address === n.address) ? .2 : 1}>
            <circle cx={n.x} cy={n.y} r={n.count > 1 ? 12 : 8} fill="#0b1729" stroke={tone(n.score)} strokeWidth={focus === n.address ? 3 : 1.7} />
            <circle cx={n.x} cy={n.y} r="3" fill={tone(n.score)} />
            {(n.count > 1 || focus === n.address) && <text x={n.x + 15} y={n.y + 4} fontSize="10" fill="#cbd5e1">{short(n.address)}</text>}
            <title>{n.address} · Highest observed risk {n.score} · {n.count} connections</title>
          </g>)}
        </svg> : <div className="h-72 flex items-center justify-center text-slate-500 text-sm px-5 text-center">No flagged transfer relationships in the current live sample.</div>}
      </div>
      <div className="px-6 pb-5 flex flex-wrap gap-4 text-xs text-slate-400">
        <span><i className="inline-block w-2.5 h-2.5 rounded-full bg-rose-400 mr-2" />Critical 80+</span>
        <span><i className="inline-block w-2.5 h-2.5 rounded-full bg-orange-400 mr-2" />High 40+</span>
        <span><i className="inline-block w-2.5 h-2.5 rounded-full bg-yellow-400 mr-2" />Elevated 20+</span>
        <span className="ml-auto text-slate-500">Connections are observed transfers, not proof of illicit activity.</span>
      </div>
    </section>
  );
}
