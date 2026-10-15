import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 8)}…${value.slice(-6)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const COLORS = {
  root: '#22d3ee',
  high: '#fb7185',
  medium: '#fbbf24',
  normal: '#60a5fa',
  entity: '#34d399',
  edge: '#64748b',
  active: '#f8fafc',
};

function numericValue(value) {
  const parsed = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function aggregate(transactions, root) {
  const rootId = norm(root);
  const byPair = new Map();
  const nodes = new Map();

  function ensureNode(id) {
    const key = norm(id);
    if (!key) return null;
    if (!nodes.has(key)) nodes.set(key, {
      id: key,
      incoming: 0,
      outgoing: 0,
      incomingValue: 0,
      outgoingValue: 0,
      txCount: 0,
      counterparties: new Set(),
      maxRisk: null,
    });
    return nodes.get(key);
  }

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;
    const value = numericValue(tx.value);
    const asset = tx.asset || 'ETH';
    const key = `${source}|${target}|${asset}`;
    if (!byPair.has(key)) byPair.set(key, {
      id: key,
      source,
      target,
      asset,
      totalValue: 0,
      txCount: 0,
      maxRisk: null,
      transactions: [],
    });
    const edge = byPair.get(key);
    edge.totalValue += value;
    edge.txCount += 1;
    if (tx.risk_score != null) edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);
    edge.transactions.push(tx);

    const from = ensureNode(source);
    const to = ensureNode(target);
    from.outgoing += 1;
    from.outgoingValue += value;
    from.txCount += 1;
    from.counterparties.add(target);
    to.incoming += 1;
    to.incomingValue += value;
    to.txCount += 1;
    to.counterparties.add(source);
    if (tx.risk_score != null) {
      const score = Number(tx.risk_score) || 0;
      from.maxRisk = Math.max(from.maxRisk ?? 0, score);
      to.maxRisk = Math.max(to.maxRisk ?? 0, score);
    }
  }

  const adjacency = new Map();
  for (const id of nodes.keys()) adjacency.set(id, new Set());
  for (const edge of byPair.values()) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }

  const depth = new Map();
  if (rootId && nodes.has(rootId)) {
    depth.set(rootId, 0);
    const queue = [rootId];
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      const nextDepth = (depth.get(current) ?? 0) + 1;
      for (const neighbor of adjacency.get(current) || []) {
        if (!depth.has(neighbor)) {
          depth.set(neighbor, nextDepth);
          queue.push(neighbor);
        }
      }
    }
  }

  const list = [...nodes.values()];
  const rootNode = nodes.get(rootId);
  const others = list.filter(node => node.id !== rootId).sort((a, b) => b.txCount - a.txCount);
  const positioned = [];
  if (rootNode) positioned.push({ ...rootNode, depth: 0, x: 0, y: 0, z: 0, isRoot: true });
  others.forEach((node, index) => {
    const d = depth.get(node.id) ?? 2;
    const ring = Math.max(1, d);
    const countAtDepth = Math.max(1, others.filter(item => (depth.get(item.id) ?? 2) === d).length);
    const indexAtDepth = others.filter(item => (depth.get(item.id) ?? 2) === d).indexOf(node);
    const angle = (indexAtDepth / countAtDepth) * Math.PI * 2 + ring * 0.55;
    const radius = 150 + ring * 135;
    const wave = ((index % 5) - 2) * 48;
    positioned.push({
      ...node,
      depth: d,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius * 0.72,
      z: Math.sin(angle * 1.7) * 150 + wave,
      isRoot: false,
    });
  });
  if (!rootNode) {
    list.forEach((node, index) => {
      const angle = (index / Math.max(1, list.length)) * Math.PI * 2;
      const radius = 160 + 90 * Math.sqrt(index);
      positioned.push({ ...node, depth: 1, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius * .7, z: Math.sin(angle * 1.4) * 140, isRoot: false });
    });
  }

  return { nodes: positioned, edges: [...byPair.values()], root: rootId };
}

function riskColor(score, isRoot) {
  if (isRoot) return COLORS.root;
  if (score == null) return COLORS.normal;
  if (score >= 70) return COLORS.high;
  if (score >= 40) return COLORS.medium;
  return COLORS.normal;
}

function rotate(point, yaw, pitch) {
  const cosy = Math.cos(yaw), siny = Math.sin(yaw);
  const x1 = point.x * cosy - point.z * siny;
  const z1 = point.x * siny + point.z * cosy;
  const cosp = Math.cos(pitch), sinp = Math.sin(pitch);
  return {
    x: x1,
    y: point.y * cosp - z1 * sinp,
    z: point.y * sinp + z1 * cosp,
  };
}

function project(point, width, height, yaw, pitch, zoom) {
  const rotated = rotate(point, yaw, pitch);
  const camera = 900;
  const depth = camera + rotated.z;
  const scale = clamp((camera / Math.max(250, depth)) * zoom, .16, 5);
  return { x: width / 2 + rotated.x * scale, y: height / 2 + rotated.y * scale, z: rotated.z, scale };
}

export default function FlowGraph3D({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });
  const [yaw, setYaw] = useState(-0.45);
  const [pitch, setPitch] = useState(0.24);
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState('');
  const [minValue, setMinValue] = useState(0);
  const [maxDepth, setMaxDepth] = useState(3);
  const [showParticles, setShowParticles] = useState(true);
  const [mode, setMode] = useState('3d');
  const network = useMemo(() => aggregate(transactions, root), [transactions, root]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const allowedNodes = new Set(network.nodes.filter(node => node.depth <= maxDepth && (!q || node.id.includes(q))).map(node => node.id));
    const matchingEdges = network.edges.filter(edge => {
      if (edge.totalValue < Number(minValue || 0)) return false;
      const sourceNode = network.nodes.find(node => node.id === edge.source);
      const targetNode = network.nodes.find(node => node.id === edge.target);
      if ((sourceNode?.depth ?? 9) > maxDepth || (targetNode?.depth ?? 9) > maxDepth) return false;
      if (!q) return true;
      return edge.source.includes(q) || edge.target.includes(q) || edge.transactions.some(tx => String(tx.hash).toLowerCase().includes(q));
    });
    if (q) matchingEdges.forEach(edge => { allowedNodes.add(edge.source); allowedNodes.add(edge.target); });
    return {
      nodes: network.nodes.filter(node => allowedNodes.has(node.id)),
      edges: matchingEdges,
    };
  }, [network, query, minValue, maxDepth]);

  const selectedNode = selected?.kind === 'node' ? network.nodes.find(node => node.id === selected.id) : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;

  useEffect(() => {
    if (mode !== '3d') return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let active = true;

    const draw = time => {
      if (!active) return;
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const gradient = ctx.createRadialGradient(width * .5, height * .48, 40, width * .5, height * .5, Math.max(width, height) * .7);
      gradient.addColorStop(0, '#10223c');
      gradient.addColorStop(1, '#050b16');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      ctx.globalAlpha = .26;
      ctx.strokeStyle = '#1e3a5f';
      ctx.lineWidth = 1;
      for (let x = -width; x < width * 2; x += 42) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x - 180, height); ctx.stroke();
      }
      for (let y = 20; y < height; y += 38) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
      }
      ctx.globalAlpha = 1;

      const projection = new Map();
      filtered.nodes.forEach(node => projection.set(node.id, project(node, width, height, yaw, pitch, zoom)));
      const edgeHits = [];
      const maxEdge = Math.max(1, ...filtered.edges.map(edge => edge.totalValue));

      [...filtered.edges].sort((a, b) => {
        const ap = projection.get(a.source), bp = projection.get(b.source);
        return (ap?.z || 0) - (bp?.z || 0);
      }).forEach((edge, edgeIndex) => {
        const a = projection.get(edge.source), b = projection.get(edge.target);
        if (!a || !b) return;
        const isActive = selectedEdge?.id === edge.id;
        const ratio = Math.log10(edge.totalValue + 1) / Math.log10(maxEdge + 1 || 2);
        ctx.strokeStyle = isActive ? COLORS.active : COLORS.edge;
        ctx.globalAlpha = isActive ? .95 : .28 + ratio * .42;
        ctx.lineWidth = isActive ? 3.5 : 1.2 + ratio * 4.3;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        ctx.globalAlpha = 1;

        if (showParticles) {
          const phase = ((time * .00018 * (1 + edgeIndex % 4)) + edgeIndex * .17) % 1;
          const px = a.x + (b.x - a.x) * phase;
          const py = a.y + (b.y - a.y) * phase;
          ctx.fillStyle = isActive ? '#ffffff' : '#22d3ee';
          ctx.shadowColor = '#22d3ee'; ctx.shadowBlur = 10;
          ctx.beginPath(); ctx.arc(px, py, isActive ? 3.7 : 2.6, 0, Math.PI * 2); ctx.fill();
          ctx.shadowBlur = 0;
        }
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      });

      const nodeHits = [];
      [...filtered.nodes].sort((a, b) => (projection.get(a.id)?.z || 0) - (projection.get(b.id)?.z || 0)).forEach(node => {
        const p = projection.get(node.id);
        if (!p) return;
        const activeNode = selectedNode?.id === node.id;
        const radius = clamp((node.isRoot ? 13 : 7 + Math.min(node.counterparties.size, 6)) * Math.sqrt(p.scale), 5, 24);
        const color = riskColor(node.maxRisk, node.isRoot);
        ctx.shadowColor = color; ctx.shadowBlur = activeNode ? 28 : 13;
        ctx.fillStyle = '#07101f'; ctx.strokeStyle = color; ctx.lineWidth = activeNode ? 4 : 2;
        ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.fillStyle = color; ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(2.5, radius * .28), 0, Math.PI * 2); ctx.fill();
        if (node.isRoot || activeNode || node.txCount >= 3) {
          ctx.font = `${activeNode ? 12 : 11}px ui-monospace, SFMono-Regular, Menlo, monospace`;
          ctx.fillStyle = '#e2e8f0';
          ctx.fillText(short(node.id), p.x + radius + 8, p.y + 4);
        }
        nodeHits.push({ id: node.id, x: p.x, y: p.y, r: radius + 8 });
      });
      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frameRef.current = requestAnimationFrame(draw);
    };
    frameRef.current = requestAnimationFrame(draw);
    return () => { active = false; if (frameRef.current) cancelAnimationFrame(frameRef.current); };
  }, [filtered, yaw, pitch, zoom, selectedNode?.id, selectedEdge?.id, showParticles, mode]);

  function distanceToSegment(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay;
    const len2 = dx * dx + dy * dy || 1;
    const t = clamp(((px - ax) * dx + (py - ay) * dy) / len2, 0, 1);
    const x = ax + t * dx, y = ay + t * dy;
    return Math.hypot(px - x, py - y);
  }

  function pointerPosition(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function pointerDown(event) {
    const p = pointerPosition(event);
    const node = [...hitRef.current.nodes].reverse().find(hit => Math.hypot(p.x - hit.x, p.y - hit.y) <= hit.r);
    if (node) { setSelected({ kind: 'node', id: node.id }); return; }
    const edge = [...hitRef.current.edges].reverse().find(hit => distanceToSegment(p.x, p.y, hit.ax, hit.ay, hit.bx, hit.by) <= 8);
    if (edge) { setSelected({ kind: 'edge', id: edge.id }); return; }
    dragRef.current = { x: event.clientX, y: event.clientY, yaw, pitch };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function pointerMove(event) {
    if (!dragRef.current) return;
    setYaw(dragRef.current.yaw + (event.clientX - dragRef.current.x) * .007);
    setPitch(clamp(dragRef.current.pitch + (event.clientY - dragRef.current.y) * .006, -1.15, 1.15));
  }

  const relatedEdges = selectedNode ? network.edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id) : [];
  const selectedAssetValue = selectedEdge ? `${selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${selectedEdge.asset}` : '';

  return <section className="overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-950/70 shadow-2xl shadow-black/20">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
      <div><p className="eyebrow">3D flow intelligence</p><h3 className="mt-1 text-lg font-semibold text-white">Interactive fund-flow network</h3></div>
      <div className="text-xs text-slate-400">{filtered.nodes.length} wallets · {filtered.edges.length} aggregated relationships</div>
    </div>

    <div className="grid gap-3 border-b border-slate-800 bg-slate-950/70 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_160px_150px_auto]">
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Wallet or transaction hash…" className="soft-input font-mono text-xs" />
      <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} aria-label="Minimum transfer value" className="soft-input text-xs" placeholder="Min value" />
      <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="soft-input text-xs" aria-label="Maximum hop depth">
        <option value={1}>1 hop</option><option value={2}>2 hops</option><option value={3}>3 hops</option><option value={9}>All loaded</option>
      </select>
      <div className="flex gap-2">
        <button type="button" onClick={() => setMode(mode === '3d' ? 'table' : '3d')} className="secondary-button text-xs">{mode === '3d' ? 'Table' : '3D graph'}</button>
        <button type="button" onClick={() => setShowParticles(value => !value)} className="secondary-button text-xs">Flow {showParticles ? 'on' : 'off'}</button>
      </div>
    </div>

    {mode === '3d' ? <div className="grid lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="relative min-h-[560px] bg-[#050b16]">
        <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
          <button type="button" onClick={() => setZoom(value => clamp(value + .16, .35, 2.5))} className="secondary-button px-3 py-1.5 text-xs">+</button>
          <button type="button" onClick={() => setZoom(value => clamp(value - .16, .35, 2.5))} className="secondary-button px-3 py-1.5 text-xs">−</button>
          <button type="button" onClick={() => { setYaw(-.45); setPitch(.24); setZoom(1); }} className="secondary-button px-3 py-1.5 text-xs">Reset camera</button>
        </div>
        <canvas ref={canvasRef} className="h-[560px] w-full touch-none cursor-grab active:cursor-grabbing" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }} onWheel={event => { event.preventDefault(); setZoom(value => clamp(value + (event.deltaY < 0 ? .08 : -.08), .35, 2.5)); }} />
        {!filtered.nodes.length && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">No loaded relationships match these filters.</div>}
        <div className="pointer-events-none absolute bottom-3 left-4 rounded-full border border-slate-700 bg-slate-950/75 px-3 py-1.5 text-[11px] text-slate-400">Drag empty space to rotate · wheel to zoom · click wallet or flow</div>
      </div>

      <aside className="border-t border-slate-800 bg-slate-950/65 p-5 lg:border-l lg:border-t-0">
        <p className="eyebrow">Investigation details</p>
        {!selected && <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-sm leading-6 text-slate-400">Select a wallet or transfer relationship. Edge thickness represents observed value; moving particles show direction.</div>}
        {selectedNode && <div className="mt-4 space-y-4">
          <div><p className="text-xs text-slate-500">Wallet</p><a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-1 block break-all font-mono text-xs text-cyan-300 hover:underline">{selectedNode.id} ↗</a></div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-xl font-semibold text-cyan-300">{selectedNode.incoming}</p><p className="text-slate-500">Incoming tx</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-xl font-semibold text-violet-300">{selectedNode.outgoing}</p><p className="text-slate-500">Outgoing tx</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-lg font-semibold text-white">{selectedNode.counterparties.size}</p><p className="text-slate-500">Counterparties</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-lg font-semibold text-white">{selectedNode.depth}</p><p className="text-slate-500">Hop depth</p></div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/45 p-3 text-xs text-slate-400">
            <div className="flex justify-between gap-3"><span>Observed in</span><span className="font-mono text-slate-200">{selectedNode.incomingValue.toLocaleString(undefined, { maximumFractionDigits: 8 })}</span></div>
            <div className="mt-2 flex justify-between gap-3"><span>Observed out</span><span className="font-mono text-slate-200">{selectedNode.outgoingValue.toLocaleString(undefined, { maximumFractionDigits: 8 })}</span></div>
            <div className="mt-2 flex justify-between gap-3"><span>Risk</span><span className="text-slate-200">{selectedNode.maxRisk == null ? 'Not assessed' : selectedNode.maxRisk}</span></div>
          </div>
          <div><p className="mb-2 text-xs font-medium text-slate-300">Observed relationships</p><div className="max-h-48 space-y-2 overflow-auto pr-1">{relatedEdges.slice(0, 12).map(edge => <button key={edge.id} type="button" onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-left text-[11px] text-slate-400 hover:border-cyan-500/40"><span className="font-mono text-slate-300">{short(edge.source)} → {short(edge.target)}</span><span className="mt-1 block">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 6 })} {edge.asset} · {edge.txCount} tx</span></button>)}</div></div>
        </div>}

        {selectedEdge && <div className="mt-4 space-y-4">
          <div><p className="text-xs text-slate-500">Transfer relationship</p><p className="mt-1 font-mono text-xs text-slate-300">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div>
          <div className="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4"><p className="text-xs text-slate-500">Observed transferred value</p><p className="mt-2 text-2xl font-semibold text-cyan-300">{selectedAssetValue}</p><p className="mt-1 text-xs text-slate-500">Across {selectedEdge.txCount} loaded transaction{selectedEdge.txCount === 1 ? '' : 's'}</p></div>
          <div className="space-y-2 text-xs text-slate-400"><p>From <span className="break-all font-mono text-slate-200">{selectedEdge.source}</span></p><p>To <span className="break-all font-mono text-slate-200">{selectedEdge.target}</span></p><p>Max loaded risk <span className="text-slate-200">{selectedEdge.maxRisk == null ? 'Not assessed' : selectedEdge.maxRisk}</span></p></div>
          <div><p className="mb-2 text-xs font-medium text-slate-300">Evidence transactions</p><div className="max-h-56 space-y-2 overflow-auto pr-1">{selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-left hover:border-cyan-500/40"><span className="block font-mono text-[11px] text-cyan-300">{short(tx.hash)} ↗</span><span className="mt-1 block text-[11px] text-slate-500">{tx.value} {tx.asset || ''} · {tx.category || 'transfer'}</span></button>)}</div></div>
        </div>}
      </aside>
    </div> : <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs"><thead className="border-b border-slate-800 bg-slate-950 text-slate-500"><tr><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Observed value</th><th className="px-4 py-3">Tx count</th><th className="px-4 py-3">Evidence</th></tr></thead><tbody>{filtered.edges.map(edge => <tr key={edge.id} className="border-b border-slate-900 text-slate-300"><td className="px-4 py-3 font-mono">{short(edge.source)}</td><td className="px-4 py-3 font-mono">{short(edge.target)}</td><td className="px-4 py-3">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {edge.asset}</td><td className="px-4 py-3">{edge.txCount}</td><td className="px-4 py-3"><button type="button" onClick={() => { setSelected({ kind: 'edge', id: edge.id }); setMode('3d'); }} className="text-cyan-300 hover:underline">Inspect</button></td></tr>)}</tbody></table>
    </div>}

    <div className="border-t border-amber-500/10 bg-amber-400/[0.035] px-4 py-3 text-[11px] leading-5 text-amber-200/80">Observed loaded ChainScope evidence only. Aggregated values represent the currently loaded transfer sample and must not be interpreted as complete lifetime wallet totals.</div>
  </section>;
}
