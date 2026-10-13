import { useMemo, useRef, useState } from 'react';

const short = value => value ? value.slice(0, 8) + '…' + value.slice(-5) : '—';
const normalized = value => (value || '').toLowerCase();
const palette = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#fb7185', '#2dd4bf'];
const riskText = score => score == null ? 'Not assessed' : String(score);

function makeNetwork(transactions) {
  const edges = transactions.filter(t => t.from_address && t.to_address && t.hash).map((t, index) => ({
    id: t.hash + '-' + index, from: normalized(t.from_address), to: normalized(t.to_address), tx: t,
  }));
  const adjacency = new Map();
  edges.forEach(edge => {
    if (!adjacency.has(edge.from)) adjacency.set(edge.from, new Set());
    if (!adjacency.has(edge.to)) adjacency.set(edge.to, new Set());
    adjacency.get(edge.from).add(edge.to);
    adjacency.get(edge.to).add(edge.from);
  });
  const visited = new Set();
  const clusters = [];
  for (const address of [...adjacency.keys()].sort()) {
    if (visited.has(address)) continue;
    const group = [];
    const queue = [address];
    visited.add(address);
    for (let i = 0; i < queue.length; i++) {
      const current = queue[i];
      group.push(current);
      for (const neighbor of adjacency.get(current)) {
        if (!visited.has(neighbor)) { visited.add(neighbor); queue.push(neighbor); }
      }
    }
    clusters.push(group.sort((a, b) => adjacency.get(b).size - adjacency.get(a).size || a.localeCompare(b)));
  }
  clusters.sort((a, b) => b.length - a.length);
  const nodes = [];
  const positions = new Map();
  clusters.forEach((group, cluster) => {
    const angle = cluster * 2.399963229728653;
    const distance = cluster === 0 ? 0 : 210 * Math.sqrt(cluster);
    const cx = 500 + Math.cos(angle) * distance;
    const cy = 360 + Math.sin(angle) * distance;
    group.forEach((address, i) => {
      const theta = (i * 2.399963229728653) + cluster;
      const radius = i === 0 ? 0 : 62 * Math.sqrt(i);
      const node = { id: address, x: cx + Math.cos(theta) * radius, y: cy + Math.sin(theta) * radius, cluster, degree: adjacency.get(address).size };
      nodes.push(node);
      positions.set(address, node);
    });
  });
  return { nodes, edges, positions, clusters };
}

export default function InvestigationGraph({ transactions = [], onSelect }) {
  const [mode, setMode] = useState('graph');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef(null);
  const network = useMemo(() => makeNetwork(transactions), [transactions]);
  const selectedNode = selected?.kind === 'node' ? selected.id : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const ids = new Set();
    network.edges.forEach(edge => {
      if ([edge.from, edge.to, edge.tx.hash].some(value => value.includes(q))) {
        ids.add(edge.from); ids.add(edge.to);
      }
    });
    network.nodes.forEach(node => { if (node.id.includes(q)) ids.add(node.id); });
    return ids;
  }, [query, network]);
  const related = selectedNode ? network.edges.filter(edge => edge.from === selectedNode || edge.to === selectedNode) : [];
  const focus = selectedNode || (selectedEdge && selectedEdge.from);
  const visibleEdges = network.edges.filter(edge => !matches || (matches.has(edge.from) && matches.has(edge.to)));
  const exportEvidence = () => {
    const quote = value => '"' + String(value ?? '').replace(/"/g, '""') + '"';
    const rows = [
      ['transaction_hash', 'from_address', 'to_address', 'value', 'asset', 'category', 'risk_score', 'evidence_url'],
      ...visibleEdges.map(({ tx, from, to }) => [
        tx.hash, from, to, tx.value, tx.asset, tx.category, tx.risk_score,
        tx.evidence_url || 'https://etherscan.io/tx/' + tx.hash,
      ]),
    ];
    const csv = rows.map(row => row.map(quote).join(',')).join('\\r\\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'chainscope-observed-transfers.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };
  const zoom = delta => setScale(current => Math.max(0.45, Math.min(3, +(current + delta).toFixed(2))));
  const reset = () => { setScale(1); setOffset({ x: 0, y: 0 }); setSelected(null); setQuery(''); };
  const pointerDown = event => {
    if (event.button !== 0 || event.target.closest('[data-network-node]')) return;
    drag.current = { x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = event => {
    if (!drag.current) return;
    setOffset({ x: drag.current.ox + event.clientX - drag.current.x, y: drag.current.oy + event.clientY - drag.current.y });
  };
  const stopDrag = () => { drag.current = null; };
  return (
    <section className="rounded-lg border border-slate-700 bg-slate-800 overflow-hidden">
      <div className="px-5 py-5 border-b border-slate-700 flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-lg font-semibold text-white">Investigation workspace</h2>
          <p className="text-sm text-slate-400 mt-1">Explore observed transfers from the selected wallet query or flagged feed.</p></div>
        <div className="text-sm text-slate-400">{network.nodes.length} wallets · {network.edges.length} transfers · {network.clusters.length} connected groups</div>
      </div>
      <div className="px-5 py-3 flex flex-wrap gap-3 items-center border-b border-slate-700">
        <input aria-label="Find wallet or transaction" value={query} onChange={event => setQuery(event.target.value)}
          placeholder="Find wallet address or transaction hash…" className="flex-1 min-w-[220px] bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-sky-400"/>
        <button type="button" onClick={exportEvidence} disabled={!visibleEdges.length} className="rounded-lg border border-sky-700 px-3 py-2 text-sm text-sky-300 disabled:opacity-40">Export visible evidence CSV</button>
        <div className="flex rounded-lg border border-slate-600 overflow-hidden text-sm">
          <button onClick={() => setMode('graph')} aria-pressed={mode === 'graph'} className={`px-4 py-2 ${mode === 'graph' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>Network</button>
          <button onClick={() => setMode('table')} aria-pressed={mode === 'table'} className={`px-4 py-2 ${mode === 'table' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>Table</button>
        </div>
      </div>
      {mode === 'graph' ? <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="relative bg-[#0a1426] overflow-hidden min-h-[490px]">
          <div className="absolute top-3 left-3 z-10 flex gap-2">
            <button aria-label="Zoom in" onClick={() => zoom(.2)} className="bg-slate-800 border border-slate-600 rounded px-3 py-1 text-white">+</button>
            <button aria-label="Zoom out" onClick={() => zoom(-.2)} className="bg-slate-800 border border-slate-600 rounded px-3 py-1 text-white">−</button>
            <button onClick={reset} className="bg-slate-800 border border-slate-600 rounded px-3 py-1 text-sm text-white">Reset</button>
          </div>
          <svg viewBox="0 0 1000 720" className="w-full h-[490px] lg:h-[590px] touch-none cursor-grab" role="img"
            aria-label="Interactive observed Ethereum transfer network. Select a node or edge to inspect evidence."
            onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={stopDrag} onPointerCancel={stopDrag}
            onWheel={event => { if (event.ctrlKey) zoom(event.deltaY < 0 ? .1 : -.1); }}>
            <defs><marker id="network-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#94a3b8" strokeWidth="1.2"/></marker><pattern id="network-grid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#1e3a5f"/></pattern></defs>
            <rect width="1000" height="720" fill="url(#network-grid)"/>
            <g transform={`translate(${offset.x} ${offset.y}) translate(500 360) scale(${scale}) translate(-500 -360)`}>
              {visibleEdges.map(edge => {
                const a = network.positions.get(edge.from), b = network.positions.get(edge.to);
                if (!a || !b) return null;
                const active = selectedEdge?.id === edge.id || (focus && (edge.from === focus || edge.to === focus));
                return <g key={edge.id}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active ? '#fbbf24' : palette[a.cluster % palette.length]} strokeOpacity={active ? .95 : .38} strokeWidth={active ? 3 : 1.6} markerEnd="url(#network-arrow)"/>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="16" className="cursor-pointer" onClick={() => setSelected({ kind: 'edge', id: edge.id })}/>
                </g>;
              })}
              {network.nodes.filter(node => !matches || matches.has(node.id)).map(node => {
                const active = selectedNode === node.id;
                const dim = focus && !active && !related.some(edge => edge.from === node.id || edge.to === node.id);
                return <g key={node.id} data-network-node="true" className="cursor-pointer" onClick={() => setSelected({ kind: 'node', id: node.id })}>
                  <circle cx={node.x} cy={node.y} r={active ? 23 : 11 + Math.min(node.degree, 7) * 2} fill="#0a1426" stroke={palette[node.cluster % palette.length]} strokeWidth={active ? 4 : 2.5} opacity={dim ? .35 : 1}/>
                  <circle cx={node.x} cy={node.y} r="4" fill={palette[node.cluster % palette.length]} opacity={dim ? .35 : 1}/>
                  {(active || node.degree >= 3) && <text x={node.x + 21} y={node.y + 5} fill="#e2e8f0" fontSize="14" stroke="#0a1426" strokeWidth="3" paintOrder="stroke">{short(node.id)}</text>}
                  <title>{node.id} · {node.degree} connected wallets</title>
                </g>;
              })}
            </g>
          </svg>
          {network.nodes.length === 0 && <p className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">No observed connections in the loaded transfer sample.</p>}
          <p className="absolute bottom-3 left-4 text-xs text-slate-400 pointer-events-none">Drag canvas to pan · use +/− to zoom · click a node or connection</p>
        </div>
        <aside className="border-t lg:border-t-0 lg:border-l border-slate-700 p-5 space-y-4">
          <h3 className="font-semibold text-white">Investigation details</h3>
          {selectedNode ? <>
            <p className="text-xs text-slate-400">Selected wallet</p><p className="text-xs font-mono break-all text-sky-300">{selectedNode}</p>
            <p className="text-sm text-slate-300">{related.length} observed transfers involving this wallet</p>
            <div className="space-y-2 max-h-64 overflow-auto">{related.slice(0, 20).map(edge => <button key={edge.id} onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="block text-left text-xs text-sky-300 hover:underline">{short(edge.tx.hash)} · {edge.tx.value ?? '—'} {edge.tx.asset || (edge.tx.category === 'external' ? 'ETH' : '')}</button>)}</div>
            <a href={`https://etherscan.io/address/${selectedNode}`} target="_blank" rel="noopener noreferrer" className="block text-sm text-sky-400 hover:underline">View wallet on Etherscan ↗</a>
          </> : selectedEdge ? <>
            <p className="text-xs text-slate-400">Observed transfer</p>
            <p className="text-xs font-mono break-all text-slate-200">{selectedEdge.from}</p><p className="text-sky-400">↓</p>
            <p className="text-xs font-mono break-all text-slate-200">{selectedEdge.to}</p>
            <p className="text-sm text-slate-300">Value: {selectedEdge.tx.value ?? '—'} {selectedEdge.tx.asset || (selectedEdge.tx.category === 'external' ? 'ETH' : '')}</p>
            <p className="text-sm text-slate-300">Risk indicator: {riskText(selectedEdge.tx.risk_score)}</p>
            <a href={`https://etherscan.io/tx/${selectedEdge.tx.hash}`} target="_blank" rel="noopener noreferrer" className="block text-sm text-sky-400 hover:underline">View transaction evidence ↗</a>
            <button onClick={() => onSelect?.(selectedEdge.tx)} className="rounded-lg bg-slate-700 px-3 py-2 text-sm hover:bg-slate-600">Transaction details</button>
          </> : <p className="text-sm text-slate-400">Select a wallet or connection to inspect its observed activity and source transaction.</p>}
          <div className="border-t border-slate-700 pt-3 text-xs text-slate-400">Colors distinguish connected components, not known owners or criminal groups. Layout is based only on the loaded sample.</div>
        </aside>
      </div> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-900/50 text-slate-400"><tr><th className="p-4">Sender</th><th className="p-4">Recipient</th><th className="p-4">Amount / asset</th><th className="p-4">Risk</th><th className="p-4">Evidence</th></tr></thead>
        <tbody className="divide-y divide-slate-700">{visibleEdges.map(edge => <tr key={edge.id} className="hover:bg-slate-700/40"><td className="p-4 font-mono">{short(edge.from)}</td><td className="p-4 font-mono">{short(edge.to)}</td><td className="p-4">{edge.tx.value ?? "—"} {edge.tx.asset || (edge.tx.category === "external" ? "ETH" : "")}</td><td className="p-4">{riskText(edge.tx.risk_score)}</td><td className="p-4"><button className="text-sky-400 hover:underline" onClick={() => onSelect?.(edge.tx)}>{short(edge.tx.hash)} ↗</button></td></tr>)}</tbody></table>
        {visibleEdges.length === 0 && <p className="p-8 text-sm text-slate-400">No matching transfers in the current sample.</p>}
      </div>}
      <p className="px-5 py-3 text-xs text-slate-500 border-t border-slate-700">Connections are observed transfers, not proof of shared ownership, illicit behavior, or complete transaction history.</p>
    </section>
  );
}
