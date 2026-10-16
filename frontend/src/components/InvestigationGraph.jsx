import { useMemo, useRef, useState } from 'react';

const short = value => value ? value.slice(0, 8) + '…' + value.slice(-5) : '—';
const normalized = value => (value || '').toLowerCase();
const palette = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#fb7185', '#2dd4bf'];
const riskText = score => score == null ? 'Not assessed' : String(score);

function makeNetwork(transactions) {
  const edges = transactions
    .filter(t => t.from_address && t.to_address && t.hash)
    .map((t, index) => ({ id: `${t.hash}-${t.category || t.asset || 'tx'}-${index}`, from: normalized(t.from_address), to: normalized(t.to_address), tx: t }));

  const adjacency = new Map();
  edges.forEach(edge => {
    if (!adjacency.has(edge.from)) adjacency.set(edge.from, new Set());
    if (!adjacency.has(edge.to)) adjacency.set(edge.to, new Set());
    adjacency.get(edge.from).add(edge.to);
    adjacency.get(edge.to).add(edge.from);
  });

  const ids = [...adjacency.keys()].sort((a, b) => (adjacency.get(b)?.size || 0) - (adjacency.get(a)?.size || 0) || a.localeCompare(b));
  const nodes = ids.map((id, index) => {
    const golden = Math.PI * (3 - Math.sqrt(5));
    const radius = 85 + 24 * Math.sqrt(index);
    const y = 1 - (index / Math.max(1, ids.length - 1)) * 2;
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * index;
    return {
      id,
      x: Math.cos(theta) * ring * radius,
      y: y * radius * 0.9,
      z: Math.sin(theta) * ring * radius,
      cluster: index % palette.length,
      degree: adjacency.get(id)?.size || 0,
    };
  });
  const positions = new Map(nodes.map(node => [node.id, node]));
  return { nodes, edges, positions };
}

function rotatePoint(point, rotation) {
  const cx = Math.cos(rotation.x), sx = Math.sin(rotation.x);
  const cy = Math.cos(rotation.y), sy = Math.sin(rotation.y);
  const y1 = point.y * cx - point.z * sx;
  const z1 = point.y * sx + point.z * cx;
  const x2 = point.x * cy + z1 * sy;
  const z2 = -point.x * sy + z1 * cy;
  return { x: x2, y: y1, z: z2 };
}

function projectPoint(point, rotation, zoom) {
  const rotated = rotatePoint(point, rotation);
  const camera = 760;
  const perspective = camera / Math.max(260, camera - rotated.z);
  return {
    x: 500 + rotated.x * perspective * zoom,
    y: 350 + rotated.y * perspective * zoom,
    z: rotated.z,
    perspective,
  };
}

export default function InvestigationGraph({
  transactions = [],
  rootAddress = '',
  onSelect,
  onExpandAddress,
  expandingAddress = '',
  expandedAddresses = [],
  nodeContext = {},
}) {
  const [mode, setMode] = useState('graph');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [rotation, setRotation] = useState({ x: -0.18, y: 0.52 });
  const [zoom, setZoom] = useState(1.05);
  const drag = useRef(null);
  const network = useMemo(() => makeNetwork(transactions), [transactions]);
  const root = normalized(rootAddress);
  const expanded = useMemo(() => new Set(expandedAddresses.map(normalized)), [expandedAddresses]);

  const selectedNode = selected?.kind === 'node' ? selected.id : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;
  const selectedContext = selectedNode ? (nodeContext[selectedNode] || {}) : {};

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const ids = new Set();
    network.edges.forEach(edge => {
      if ([edge.from, edge.to, edge.tx.hash, edge.tx.asset, edge.tx.category].filter(Boolean).some(value => String(value).toLowerCase().includes(q))) {
        ids.add(edge.from); ids.add(edge.to);
      }
    });
    network.nodes.forEach(node => { if (node.id.includes(q)) ids.add(node.id); });
    return ids;
  }, [query, network]);

  const related = selectedNode ? network.edges.filter(edge => edge.from === selectedNode || edge.to === selectedNode) : [];
  const incoming = selectedNode ? related.filter(edge => edge.to === selectedNode) : [];
  const outgoing = selectedNode ? related.filter(edge => edge.from === selectedNode) : [];
  const counterparties = selectedNode ? new Set(related.map(edge => edge.from === selectedNode ? edge.to : edge.from)) : new Set();
  const maxRisk = related.reduce((value, edge) => Math.max(value, Number(edge.tx.risk_score || 0)), Number(selectedContext.maxRisk || 0));
  const assets = [...new Set(related.map(edge => edge.tx.asset || (edge.tx.category === 'external' ? 'ETH' : null)).filter(Boolean))];
  const focus = selectedNode || (selectedEdge && selectedEdge.from);
  const visibleEdges = useMemo(() => network.edges.filter(edge => !matches || (matches.has(edge.from) && matches.has(edge.to))), [network, matches]);
  const visibleNodes = useMemo(() => network.nodes.filter(node => !matches || matches.has(node.id)), [network, matches]);
  const projected = useMemo(() => new Map(network.nodes.map(node => [node.id, projectPoint(node, rotation, zoom)])), [network, rotation, zoom]);
  const renderedNodes = useMemo(() => [...visibleNodes].sort((a, b) => projected.get(a.id).z - projected.get(b.id).z), [visibleNodes, projected]);
  const renderedEdges = useMemo(() => visibleEdges.slice(0, 1200).sort((a, b) => {
    const az = ((projected.get(a.from)?.z || 0) + (projected.get(a.to)?.z || 0)) / 2;
    const bz = ((projected.get(b.from)?.z || 0) + (projected.get(b.to)?.z || 0)) / 2;
    return az - bz;
  }), [visibleEdges, projected]);

  const exportEvidence = () => {
    const quote = value => {
      const raw = String(value ?? '');
      const safe = /^\s*[=+@-]/.test(raw) ? `'${raw}` : raw;
      return `"${safe.replace(/"/g, '""')}"`;
    };
    const rows = [['transaction_hash', 'from_address', 'to_address', 'value', 'asset', 'category', 'risk_score', 'evidence_url'], ...visibleEdges.map(({ tx, from, to }) => [tx.hash, from, to, tx.value, tx.asset, tx.category, tx.risk_score, tx.evidence_url || `https://etherscan.io/tx/${tx.hash}`])];
    const csv = rows.map(row => row.map(quote).join(',')).join(String.fromCharCode(13, 10));
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = 'chainscope-investigation-evidence.csv';
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  };

  const resetView = () => {
    setRotation({ x: -0.18, y: 0.52 });
    setZoom(1.05);
    setSelected(null);
    setQuery('');
  };

  const pointerDown = event => {
    if (event.button !== 0 || event.target.closest('[data-network-node]') || event.target.closest('[data-network-edge]')) return;
    drag.current = { x: event.clientX, y: event.clientY, rx: rotation.x, ry: rotation.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = event => {
    if (!drag.current) return;
    const dx = event.clientX - drag.current.x;
    const dy = event.clientY - drag.current.y;
    setRotation({
      x: Math.max(-1.35, Math.min(1.35, drag.current.rx + dy * 0.008)),
      y: drag.current.ry + dx * 0.008,
    });
  };
  const stopDrag = () => { drag.current = null; };

  return <section className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900/70">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-700 px-5 py-5">
      <div>
        <p className="eyebrow">3D investigation graph</p>
        <h2 className="mt-2 text-lg font-semibold text-white">Orbit the wallet network</h2>
        <p className="mt-1 text-sm text-slate-400">Drag empty space to rotate in 3D. Select a bubble to inspect evidence and expand one observed hop.</p>
      </div>
      <div className="text-sm text-slate-400">{network.nodes.length} wallets · {network.edges.length} transfers · {expanded.size} expansions</div>
    </div>

    <div className="flex flex-wrap items-center gap-3 border-b border-slate-700 px-5 py-3">
      <input aria-label="Find wallet transaction or asset" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find wallet, transaction, or asset…" className="soft-input min-w-[220px] flex-1" />
      <button type="button" onClick={exportEvidence} disabled={!visibleEdges.length} className="secondary-button disabled:opacity-40">Export evidence CSV</button>
      <div className="flex overflow-hidden rounded-lg border border-slate-600 text-sm">
        <button type="button" onClick={() => setMode('graph')} aria-pressed={mode === 'graph'} className={`px-4 py-2 ${mode === 'graph' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>3D network</button>
        <button type="button" onClick={() => setMode('table')} aria-pressed={mode === 'table'} className={`px-4 py-2 ${mode === 'table' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>Evidence table</button>
      </div>
    </div>

    {mode === 'graph' ? <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="relative min-h-[520px] overflow-hidden bg-[radial-gradient(circle_at_50%_45%,#13294a_0%,#091423_48%,#050b14_100%)]">
        <div className="absolute left-3 top-3 z-10 flex gap-2">
          <button type="button" aria-label="Zoom in" onClick={() => setZoom(value => Math.min(2.2, value + .15))} className="rounded border border-slate-600 bg-slate-900/90 px-3 py-1 text-white">+</button>
          <button type="button" aria-label="Zoom out" onClick={() => setZoom(value => Math.max(.5, value - .15))} className="rounded border border-slate-600 bg-slate-900/90 px-3 py-1 text-white">−</button>
          <button type="button" onClick={resetView} className="rounded border border-slate-600 bg-slate-900/90 px-3 py-1 text-sm text-white">Reset 3D</button>
        </div>
        <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-full border border-cyan-400/15 bg-cyan-400/[0.05] px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-cyan-200">Drag to orbit</div>

        <svg viewBox="0 0 1000 700" className="h-[520px] w-full touch-none cursor-grab active:cursor-grabbing lg:h-[650px]" role="img" aria-label="Three-dimensional Ethereum transfer network. Drag background to rotate. Select wallet bubbles or transfer lines to inspect evidence." onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={stopDrag} onPointerCancel={stopDrag}>
          <defs>
            <filter id="bubble-glow" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <filter id="root-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="9" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <linearGradient id="depth-line" x1="0" x2="1"><stop offset="0" stopColor="#334155"/><stop offset=".5" stopColor="#64748b"/><stop offset="1" stopColor="#cbd5e1"/></linearGradient>
          </defs>

          {[0.55, 0.72, 0.9].map((factor, index) => <ellipse key={factor} cx="500" cy="350" rx={360 * factor} ry={118 * factor} fill="none" stroke="#1e3a5f" strokeOpacity={0.32 - index * .07} strokeWidth="1" strokeDasharray="5 9" />)}

          {renderedEdges.map(edge => {
            const a = projected.get(edge.from), b = projected.get(edge.to);
            if (!a || !b) return null;
            const active = selectedEdge?.id === edge.id || (focus && (edge.from === focus || edge.to === focus));
            const token = edge.tx.category === 'erc20';
            const depth = Math.max(.18, Math.min(1, ((a.perspective + b.perspective) / 2) * .7));
            return <g key={edge.id} data-network-edge="true">
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active ? '#fbbf24' : token ? '#a78bfa' : 'url(#depth-line)'} strokeOpacity={active ? .95 : token ? .72 * depth : .5 * depth} strokeWidth={active ? 3.5 : token ? 2.4 : 1.5} strokeDasharray={token ? '6 5' : undefined} />
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="15" className="cursor-pointer" onClick={event => { event.stopPropagation(); setSelected({ kind: 'edge', id: edge.id }); }} />
            </g>;
          })}

          {renderedNodes.map(node => {
            const point = projected.get(node.id);
            const active = selectedNode === node.id;
            const dim = selectedNode && !active && !related.some(edge => edge.from === node.id || edge.to === node.id);
            const context = nodeContext[node.id] || {};
            const isRoot = node.id === root;
            const isExpanded = expanded.has(node.id);
            const color = context.entityLabels?.length ? '#34d399' : isRoot ? '#38bdf8' : isExpanded ? '#fbbf24' : palette[node.cluster % palette.length];
            const base = isRoot ? 20 : 10 + Math.min(node.degree, 7) * 1.8;
            const radius = Math.max(7, base * point.perspective * (active ? 1.2 : 1));
            const opacity = dim ? .2 : Math.max(.48, Math.min(1, point.perspective));
            return <g key={node.id} data-network-node="true" role="button" tabIndex={0} aria-label={`${isRoot ? 'Root wallet' : 'Wallet'} ${node.id}. ${node.degree} observed peers.`} className="cursor-pointer outline-none" onClick={event => { event.stopPropagation(); setSelected({ kind: 'node', id: node.id }); }} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected({ kind: 'node', id: node.id }); } }}>
              <circle cx={point.x} cy={point.y} r={radius * 1.75} fill={color} opacity={active ? .13 : .06} filter="url(#bubble-glow)" />
              <circle cx={point.x} cy={point.y} r={radius} fill="#07111f" stroke={color} strokeWidth={isRoot || active ? 4 : 2.2} opacity={opacity} filter={isRoot ? 'url(#root-glow)' : 'url(#bubble-glow)'} />
              <circle cx={point.x - radius * .24} cy={point.y - radius * .28} r={radius * .38} fill={color} opacity={Math.min(.92, opacity + .1)} />
              <circle cx={point.x - radius * .38} cy={point.y - radius * .42} r={radius * .13} fill="#ffffff" opacity={.75 * opacity} />
              {(active || isRoot || node.degree >= 4) && <text x={point.x + radius + 8} y={point.y + 4} fill="#e2e8f0" fontSize={Math.max(11, 13 * point.perspective)} stroke="#07111f" strokeWidth="4" paintOrder="stroke">{isRoot ? `ROOT ${short(node.id)}` : short(node.id)}</text>}
              <title>{node.id} · {node.degree} observed peers</title>
            </g>;
          })}
        </svg>

        {!network.nodes.length && <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">No observed relationships are loaded for this wallet.</p>}
        <div className="pointer-events-none absolute bottom-3 left-4 flex flex-wrap gap-3 text-xs text-slate-400"><span>Solid = native ETH</span><span>Dashed violet = ERC-20</span><span>Green = source-labeled</span><span>Cyan = root</span><span>Amber = expanded</span></div>
      </div>

      <aside className="space-y-4 border-t border-slate-700 p-5 lg:border-l lg:border-t-0">
        <h3 className="font-semibold text-white">Selected evidence</h3>
        {selectedNode ? <>
          <div><p className="text-xs text-slate-400">Selected wallet</p><p className="mt-1 break-all font-mono text-xs text-sky-300">{selectedNode}</p></div>
          {selectedNode === root && <span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">Investigation root</span>}
          {expanded.has(selectedNode) && <span className="status-pill border-amber-400/20 bg-amber-400/[0.06] text-amber-200">Expanded</span>}
          {(selectedContext.entityLabels || []).map((label, index) => <div key={`${label.source}-${label.entity_id || label.entity_name}-${index}`} className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><p className="text-sm font-medium text-emerald-200">{label.entity_name || label.entity_id}</p><p className="mt-1 text-xs text-slate-400">Source: {label.source} · confidence {label.confidence ?? '—'}</p></div>)}
          <div className="grid grid-cols-3 gap-2 text-center text-xs"><div className="rounded bg-slate-950/60 p-2"><p className="text-lg font-semibold text-sky-300">{incoming.length}</p><p className="text-slate-400">Incoming</p></div><div className="rounded bg-slate-950/60 p-2"><p className="text-lg font-semibold text-sky-300">{outgoing.length}</p><p className="text-slate-400">Outgoing</p></div><div className="rounded bg-slate-950/60 p-2"><p className="text-lg font-semibold text-sky-300">{counterparties.size}</p><p className="text-slate-400">Peers</p></div></div>
          <div className="grid grid-cols-2 gap-2 text-xs"><div className="rounded bg-slate-950/60 p-3"><p className="text-slate-500">Max observed risk</p><p className="mt-1 text-lg font-semibold text-white">{maxRisk}</p></div><div className="rounded bg-slate-950/60 p-3"><p className="text-slate-500">Assets loaded</p><p className="mt-1 text-lg font-semibold text-white">{assets.length}</p></div></div>
          {assets.length > 0 && <p className="text-xs text-slate-400">Assets: {assets.slice(0, 8).join(', ')}</p>}
          <div className="max-h-52 space-y-2 overflow-auto" role="region" tabIndex={0} aria-label="Transactions for selected wallet">{related.slice(0, 20).map(edge => <button type="button" key={edge.id} onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="block w-full rounded-md border border-slate-800 bg-slate-950/35 px-2 py-2 text-left text-xs text-sky-300 hover:border-slate-700">{short(edge.tx.hash)} · {edge.tx.value ?? '—'} {edge.tx.asset || ''}</button>)}</div>
          {onExpandAddress && selectedNode !== root && !expanded.has(selectedNode) && <button type="button" onClick={() => onExpandAddress(selectedNode)} disabled={Boolean(expandingAddress)} className="primary-button w-full disabled:opacity-50">{normalized(expandingAddress) === selectedNode ? 'Expanding one hop…' : 'Expand one observed hop'}</button>}
          {expanded.has(selectedNode) && <p className="text-xs leading-5 text-amber-200">One-hop retained-data context for this wallet has already been merged into the graph.</p>}
          <a href={`https://etherscan.io/address/${selectedNode}`} target="_blank" rel="noopener noreferrer" className="block text-sm text-sky-400 hover:underline">Verify wallet on Etherscan ↗</a>
        </> : selectedEdge ? <>
          <p className="text-xs text-slate-400">Observed transfer</p><p className="break-all font-mono text-xs text-slate-200">{selectedEdge.from}</p><p className="text-sky-400">↓</p><p className="break-all font-mono text-xs text-slate-200">{selectedEdge.to}</p>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300"><p>Asset: <span className="text-white">{selectedEdge.tx.asset || 'ETH'}</span></p><p className="mt-1">Value: <span className="text-white">{selectedEdge.tx.value ?? '—'}</span></p><p className="mt-1">Risk indicator: <span className="text-white">{riskText(selectedEdge.tx.risk_score)}</span></p><p className="mt-1">Evidence type: <span className="text-white">{selectedEdge.tx.category || 'native'}</span></p></div>
          <a href={selectedEdge.tx.evidence_url || `https://etherscan.io/tx/${selectedEdge.tx.hash}`} target="_blank" rel="noopener noreferrer" className="block text-sm text-sky-400 hover:underline">Verify transaction ↗</a>
          {onSelect && <button type="button" onClick={() => onSelect(selectedEdge.tx)} className="secondary-button w-full">Transaction details</button>}
        </> : <p className="text-sm leading-6 text-slate-400">Rotate the 3D graph, then select a wallet bubble to inspect loaded risk, assets, entity context and neighboring evidence.</p>}
        <div className="border-t border-slate-700 pt-3 text-xs leading-5 text-slate-500">3D placement is a visualization aid. Graph expansion loads bounded retained evidence only and does not establish shared ownership, illicit behavior, taint, or complete history.</div>
      </aside>
    </div> : <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Investigation evidence table"><table className="w-full min-w-[780px] text-left text-sm"><thead className="bg-slate-950/50 text-slate-400"><tr><th className="p-4">Sender</th><th className="p-4">Recipient</th><th className="p-4">Amount / asset</th><th className="p-4">Type</th><th className="p-4">Risk</th><th className="p-4">Evidence</th></tr></thead><tbody className="divide-y divide-slate-700">{visibleEdges.map(edge => <tr key={edge.id} className="hover:bg-slate-700/30"><td className="p-4 font-mono">{short(edge.from)}</td><td className="p-4 font-mono">{short(edge.to)}</td><td className="p-4">{edge.tx.value ?? '—'} {edge.tx.asset || ''}</td><td className="p-4">{edge.tx.category || 'native'}</td><td className="p-4">{riskText(edge.tx.risk_score)}</td><td className="p-4"><a href={edge.tx.evidence_url || `https://etherscan.io/tx/${edge.tx.hash}`} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">{short(edge.tx.hash)} ↗</a></td></tr>)}</tbody></table>{!visibleEdges.length && <p className="p-8 text-sm text-slate-400">No matching transfers in the loaded evidence.</p>}</div>}
    <p className="border-t border-slate-700 px-5 py-3 text-xs text-slate-500">Native and ERC-20 edges remain separate observed evidence. 3D depth is visual only; no cross-asset value equivalence or ownership inference is applied.</p>
  </section>;
}
