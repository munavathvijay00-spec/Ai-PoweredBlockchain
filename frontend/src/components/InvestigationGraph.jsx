import { useEffect, useMemo, useRef, useState } from 'react';

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
  const visited = new Set();
  const clusters = [];
  for (const address of [...adjacency.keys()].sort()) {
    if (visited.has(address)) continue;
    const group = [];
    const queue = [address];
    visited.add(address);
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      group.push(current);
      for (const neighbor of adjacency.get(current) || []) {
        if (!visited.has(neighbor)) { visited.add(neighbor); queue.push(neighbor); }
      }
    }
    clusters.push(group.sort((a, b) => (adjacency.get(b)?.size || 0) - (adjacency.get(a)?.size || 0) || a.localeCompare(b)));
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
      const node = { id: address, x: cx + Math.cos(theta) * radius, y: cy + Math.sin(theta) * radius, cluster, degree: adjacency.get(address)?.size || 0 };
      nodes.push(node);
      positions.set(address, node);
    });
  });
  return { nodes, edges, positions, clusters };
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
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef(null);
  const network = useMemo(() => makeNetwork(transactions), [transactions]);
  const root = normalized(rootAddress);
  const expanded = useMemo(() => new Set(expandedAddresses.map(normalized)), [expandedAddresses]);

  useEffect(() => {
    if (!network.nodes.length) return;
    const xs = network.nodes.map(node => node.x);
    const ys = network.nodes.map(node => node.y);
    const minX = Math.min(...xs) - 60, maxX = Math.max(...xs) + 60;
    const minY = Math.min(...ys) - 60, maxY = Math.max(...ys) + 60;
    const fitted = Math.max(0.15, Math.min(3, 940 / Math.max(1, maxX - minX), 660 / Math.max(1, maxY - minY)));
    setScale(fitted);
    setOffset({ x: 500 - (minX + maxX) / 2 * fitted, y: 360 - (minY + maxY) / 2 * fitted });
  }, [network]);

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
  const MAX_RENDERED_EDGES = 1200;
  const renderedEdges = visibleEdges.slice(0, MAX_RENDERED_EDGES);

  const exportEvidence = () => {
    const quote = value => {
      const raw = String(value ?? '');
      const safe = /^\s*[=+@-]/.test(raw) ? `'${raw}` : raw;
      return `"${safe.replace(/"/g, '""')}"`;
    };
    const rows = [
      ['transaction_hash', 'from_address', 'to_address', 'value', 'asset', 'category', 'risk_score', 'evidence_url'],
      ...visibleEdges.map(({ tx, from, to }) => [tx.hash, from, to, tx.value, tx.asset, tx.category, tx.risk_score, tx.evidence_url || `https://etherscan.io/tx/${tx.hash}`]),
    ];
    const csv = rows.map(row => row.map(quote).join(',')).join(String.fromCharCode(13, 10));
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'chainscope-investigation-evidence.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const zoom = delta => setScale(current => Math.max(0.15, Math.min(3, +(current + delta).toFixed(2))));
  const reset = () => {
    if (network.nodes.length) {
      const xs = network.nodes.map(node => node.x), ys = network.nodes.map(node => node.y);
      const minX = Math.min(...xs) - 60, maxX = Math.max(...xs) + 60;
      const minY = Math.min(...ys) - 60, maxY = Math.max(...ys) + 60;
      const fitted = Math.max(0.15, Math.min(3, 940 / Math.max(1, maxX - minX), 660 / Math.max(1, maxY - minY)));
      setScale(fitted);
      setOffset({ x: 500 - (minX + maxX) / 2 * fitted, y: 360 - (minY + maxY) / 2 * fitted });
    } else { setScale(1); setOffset({ x: 0, y: 0 }); }
    setSelected(null); setQuery('');
  };
  const pointerDown = event => {
    if (event.button !== 0 || event.target.closest('[data-network-node]')) return;
    drag.current = { x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = event => {
    if (!drag.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    setOffset({ x: drag.current.ox + (event.clientX - drag.current.x) * 1000 / bounds.width, y: drag.current.oy + (event.clientY - drag.current.y) * 720 / bounds.height });
  };
  const stopDrag = () => { drag.current = null; };
  const selectNode = id => setSelected({ kind: 'node', id });

  return <section className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900/70">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-700 px-5 py-5">
      <div><p className="eyebrow">Interactive evidence graph</p><h2 className="mt-2 text-lg font-semibold text-white">Explore and expand observed relationships</h2><p className="mt-1 text-sm text-slate-400">Select a wallet to inspect its loaded activity and expand one additional retained-data hop.</p></div>
      <div className="text-sm text-slate-400">{network.nodes.length} wallets · {network.edges.length} transfers · {expanded.size} expansions</div>
    </div>
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-700 px-5 py-3">
      <input aria-label="Find wallet transaction or asset" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find wallet, transaction, or asset…" className="soft-input min-w-[220px] flex-1" />
      <button type="button" onClick={exportEvidence} disabled={!visibleEdges.length} className="secondary-button disabled:opacity-40">Export evidence CSV</button>
      <div className="flex overflow-hidden rounded-lg border border-slate-600 text-sm">
        <button type="button" onClick={() => setMode('graph')} aria-pressed={mode === 'graph'} className={`px-4 py-2 ${mode === 'graph' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>Network</button>
        <button type="button" onClick={() => setMode('table')} aria-pressed={mode === 'table'} className={`px-4 py-2 ${mode === 'table' ? 'bg-slate-600 text-white' : 'text-slate-300'}`}>Evidence table</button>
      </div>
    </div>
    {mode === 'graph' && visibleEdges.length > MAX_RENDERED_EDGES && <p role="status" className="bg-amber-950/40 px-5 py-2 text-xs text-amber-300">Canvas limited to {MAX_RENDERED_EDGES} of {visibleEdges.length} matching transfers for responsiveness. Table and CSV retain all loaded evidence.</p>}
    {mode === 'graph' ? <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="relative min-h-[500px] overflow-hidden bg-[#0a1426]">
        <div className="absolute left-3 top-3 z-10 flex gap-2">
          <button type="button" aria-label="Zoom in" onClick={() => zoom(.2)} className="rounded border border-slate-600 bg-slate-800 px-3 py-1 text-white">+</button>
          <button type="button" aria-label="Zoom out" onClick={() => zoom(-.2)} className="rounded border border-slate-600 bg-slate-800 px-3 py-1 text-white">−</button>
          <button type="button" onClick={reset} className="rounded border border-slate-600 bg-slate-800 px-3 py-1 text-sm text-white">Fit graph</button>
        </div>
        <svg viewBox="0 0 1000 720" className="h-[500px] w-full touch-none cursor-grab lg:h-[620px]" role="img" aria-label="Observed Ethereum transfer network. Select a wallet or transfer to inspect evidence." onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={stopDrag} onPointerCancel={stopDrag}>
          <defs><marker id="network-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#94a3b8" strokeWidth="1.2" /></marker><pattern id="network-grid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#1e3a5f" /></pattern></defs>
          <rect width="1000" height="720" fill="url(#network-grid)" />
          <g transform={`translate(${offset.x} ${offset.y}) translate(500 360) scale(${scale}) translate(-500 -360)`}>
            {renderedEdges.map(edge => {
              const a = network.positions.get(edge.from), b = network.positions.get(edge.to);
              if (!a || !b) return null;
              const active = selectedEdge?.id === edge.id || (focus && (edge.from === focus || edge.to === focus));
              const token = edge.tx.category === 'erc20';
              return <g key={edge.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active ? '#fbbf24' : token ? '#a78bfa' : palette[a.cluster % palette.length]} strokeOpacity={active ? .95 : token ? .58 : .38} strokeWidth={active ? 3 : token ? 2.3 : 1.6} strokeDasharray={token ? '5 4' : undefined} markerEnd="url(#network-arrow)" /><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="16" className="cursor-pointer" onClick={() => setSelected({ kind: 'edge', id: edge.id })} /></g>;
            })}
            {visibleNodes.map(node => {
              const active = selectedNode === node.id;
              const dim = selectedNode && !active && !related.some(edge => edge.from === node.id || edge.to === node.id);
              const context = nodeContext[node.id] || {};
              const isRoot = node.id === root;
              const isExpanded = expanded.has(node.id);
              const stroke = context.entityLabels?.length ? '#34d399' : isRoot ? '#38bdf8' : isExpanded ? '#fbbf24' : palette[node.cluster % palette.length];
              return <g key={node.id} data-network-node="true" role="button" tabIndex={0} aria-label={`${isRoot ? 'Root wallet' : 'Wallet'} ${node.id}. ${node.degree} observed peers.`} className="cursor-pointer outline-none" onClick={() => selectNode(node.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectNode(node.id); } }}>
                <circle cx={node.x} cy={node.y} r={active ? 23 : 11 + Math.min(node.degree, 7) * 2} fill="#0a1426" stroke={stroke} strokeWidth={active ? 4 : isRoot ? 3.5 : 2.5} opacity={dim ? .35 : 1} />
                <circle cx={node.x} cy={node.y} r={isRoot ? 6 : 4} fill={stroke} opacity={dim ? .35 : 1} />
                {(active || isRoot || node.degree >= 3) && <text x={node.x + 21} y={node.y + 5} fill="#e2e8f0" fontSize="14" stroke="#0a1426" strokeWidth="3" paintOrder="stroke">{isRoot ? `ROOT ${short(node.id)}` : short(node.id)}</text>}
                <title>{node.id} · {node.degree} observed peers</title>
              </g>;
            })}
          </g>
        </svg>
        {!network.nodes.length && <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">No observed relationships are loaded for this wallet.</p>}
        <div className="pointer-events-none absolute bottom-3 left-4 flex flex-wrap gap-3 text-xs text-slate-400"><span>Solid = native ETH</span><span>Dashed = ERC-20</span><span>Green node = source-labeled</span></div>
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
        </> : <p className="text-sm leading-6 text-slate-400">Select a wallet to inspect its loaded risk, assets, entity context and neighboring evidence. Select a connection to verify the underlying transaction.</p>}
        <div className="border-t border-slate-700 pt-3 text-xs leading-5 text-slate-500">Graph expansion loads bounded retained evidence only. Connections do not establish shared ownership, illicit behavior, taint, or complete transaction history.</div>
      </aside>
    </div> : <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Investigation evidence table"><table className="w-full min-w-[780px] text-left text-sm"><thead className="bg-slate-950/50 text-slate-400"><tr><th className="p-4">Sender</th><th className="p-4">Recipient</th><th className="p-4">Amount / asset</th><th className="p-4">Type</th><th className="p-4">Risk</th><th className="p-4">Evidence</th></tr></thead><tbody className="divide-y divide-slate-700">{visibleEdges.map(edge => <tr key={edge.id} className="hover:bg-slate-700/30"><td className="p-4 font-mono">{short(edge.from)}</td><td className="p-4 font-mono">{short(edge.to)}</td><td className="p-4">{edge.tx.value ?? '—'} {edge.tx.asset || ''}</td><td className="p-4">{edge.tx.category || 'native'}</td><td className="p-4">{riskText(edge.tx.risk_score)}</td><td className="p-4"><a href={edge.tx.evidence_url || `https://etherscan.io/tx/${edge.tx.hash}`} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">{short(edge.tx.hash)} ↗</a></td></tr>)}</tbody></table>{!visibleEdges.length && <p className="p-8 text-sm text-slate-400">No matching transfers in the loaded evidence.</p>}</div>}
    <p className="border-t border-slate-700 px-5 py-3 text-xs text-slate-500">Native and ERC-20 edges are separate observed evidence. No cross-asset value equivalence or ownership inference is applied.</p>
  </section>;
}
