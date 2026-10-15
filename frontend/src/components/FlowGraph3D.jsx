import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 6)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const COLORS = ['#ff0a8a', '#18c9d8', '#7c3aed', '#2563eb', '#14b8a6'];
const MUTED = '#243247';

function numericValue(value) {
  const parsed = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function buildNetwork(transactions, root) {
  const rootId = norm(root);
  const nodes = new Map();
  const edges = new Map();
  const adjacency = new Map();

  const ensureNode = id => {
    const key = norm(id);
    if (!key) return null;
    if (!nodes.has(key)) {
      nodes.set(key, {
        id: key,
        incoming: 0,
        outgoing: 0,
        incomingValue: 0,
        outgoingValue: 0,
        txCount: 0,
        counterparties: new Set(),
        maxRisk: null,
      });
      adjacency.set(key, new Set());
    }
    return nodes.get(key);
  };

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;

    const from = ensureNode(source);
    const to = ensureNode(target);
    const asset = tx.asset || 'ETH';
    const value = numericValue(tx.value);
    const key = `${source}|${target}|${asset}`;

    if (!edges.has(key)) {
      edges.set(key, {
        id: key,
        source,
        target,
        asset,
        totalValue: 0,
        txCount: 0,
        maxRisk: null,
        transactions: [],
      });
    }

    const edge = edges.get(key);
    edge.totalValue += value;
    edge.txCount += 1;
    edge.transactions.push(tx);
    if (tx.risk_score != null) edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);

    from.outgoing += 1;
    from.outgoingValue += value;
    from.txCount += 1;
    from.counterparties.add(target);
    to.incoming += 1;
    to.incomingValue += value;
    to.txCount += 1;
    to.counterparties.add(source);

    if (tx.risk_score != null) {
      const risk = Number(tx.risk_score) || 0;
      from.maxRisk = Math.max(from.maxRisk ?? 0, risk);
      to.maxRisk = Math.max(to.maxRisk ?? 0, risk);
    }

    adjacency.get(source).add(target);
    adjacency.get(target).add(source);
  }

  const depth = new Map();
  const branch = new Map();
  if (rootId && nodes.has(rootId)) {
    depth.set(rootId, 0);
    branch.set(rootId, rootId);
    const queue = [rootId];
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      for (const neighbor of adjacency.get(current) || []) {
        if (!depth.has(neighbor)) {
          depth.set(neighbor, (depth.get(current) ?? 0) + 1);
          branch.set(neighbor, current === rootId ? neighbor : branch.get(current));
          queue.push(neighbor);
        }
      }
    }
  }

  const firstHop = [...(adjacency.get(rootId) || [])]
    .sort((a, b) => (nodes.get(b)?.txCount || 0) - (nodes.get(a)?.txCount || 0));
  const branchRank = new Map(firstHop.map((id, index) => [id, index]));

  const groups = new Map();
  for (const node of nodes.values()) {
    const key = node.id === rootId ? '__root__' : (branch.get(node.id) || node.id);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }

  const clusterKeys = [...groups.keys()].filter(key => key !== '__root__');
  const clusterCenters = new Map();
  const prominent = clusterKeys.slice(0, 2);

  prominent.forEach((key, index) => {
    clusterCenters.set(key, index === 0 ? { x: -250, y: -120 } : { x: 245, y: 140 });
  });

  const remaining = clusterKeys.slice(2);
  remaining.forEach((key, index) => {
    const cols = 5;
    const row = Math.floor(index / cols);
    const col = index % cols;
    const side = row % 2 === 0 ? 1 : -1;
    const x = side * (390 + col * 115);
    const y = -280 + row * 155 + (col % 2) * 34;
    clusterCenters.set(key, { x, y });
  });

  const positioned = [];
  for (const [key, group] of groups.entries()) {
    if (key === '__root__') {
      const node = group[0];
      positioned.push({ ...node, x: 0, y: 0, depth: 0, cluster: -1, isRoot: true });
      continue;
    }

    const center = clusterCenters.get(key) || { x: 0, y: 0 };
    const cluster = branchRank.get(key) ?? 99;
    const ordered = [...group].sort((a, b) => b.txCount - a.txCount);
    const compact = cluster < 2;

    ordered.forEach((node, index) => {
      if (index === 0) {
        positioned.push({
          ...node,
          x: center.x,
          y: center.y,
          depth: depth.get(node.id) ?? 1,
          cluster,
          isRoot: false,
        });
        return;
      }

      const radius = compact ? 34 + 20 * Math.sqrt(index) : 24 + 16 * Math.sqrt(index);
      const angle = index * 2.399963229728653 + cluster * 0.27;
      positioned.push({
        ...node,
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius,
        depth: depth.get(node.id) ?? 2,
        cluster,
        isRoot: false,
      });
    });
  }

  return { nodes: positioned, edges: [...edges.values()], root: rootId };
}

function nodeColor(node) {
  if (node.cluster === 0) return COLORS[0];
  if (node.cluster === 1) return COLORS[1];
  if (node.isRoot) return '#a7f3d0';
  return MUTED;
}

function nodeRadius(node, zoom) {
  const activity = Math.log2(node.txCount + node.counterparties.size + 2);
  const worldRadius = node.isRoot ? 15 : 7 + activity * 1.8;
  return clamp(worldRadius * zoom, node.isRoot ? 7 : 4.5, node.isRoot ? 46 : 40);
}

function drawBubble(ctx, node, point, radius, selected, hovered) {
  const color = nodeColor(node);
  const muted = color === MUTED;
  const active = selected || hovered;

  ctx.save();
  ctx.globalAlpha = muted ? 0.34 : active ? 1 : 0.92;
  ctx.fillStyle = muted ? 'rgba(13,21,34,.72)' : 'rgba(4,8,18,.92)';
  ctx.strokeStyle = active ? '#ffffff' : color;
  ctx.lineWidth = active ? 2.3 : muted ? 1.1 : 2.2;
  ctx.shadowColor = muted ? 'transparent' : color;
  ctx.shadowBlur = active ? 18 : 7;
  ctx.beginPath();
  ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  if (!muted) {
    ctx.shadowBlur = 0;
    ctx.globalAlpha = active ? 0.95 : 0.62;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(point.x, point.y, Math.max(1.6, radius * 0.16), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawArrow(ctx, a, b, color, alpha) {
  const angle = Math.atan2(b.y - a.y, b.x - a.x);
  const x = a.x + (b.x - a.x) * 0.68;
  const y = a.y + (b.y - a.y) * 0.68;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(6, 0);
  ctx.lineTo(-4, -3.5);
  ctx.lineTo(-4, 3.5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function distanceToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const length2 = dx * dx + dy * dy || 1;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / length2, 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export default function FlowGraph3D({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });

  const [zoom, setZoom] = useState(0.72);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [query, setQuery] = useState('');
  const [minValue, setMinValue] = useState(0);
  const [maxDepth, setMaxDepth] = useState(3);
  const [mode, setMode] = useState('map');

  const network = useMemo(() => buildNetwork(transactions, root), [transactions, root]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const nodeById = new Map(network.nodes.map(node => [node.id, node]));
    const edges = network.edges.filter(edge => {
      if (edge.totalValue < Number(minValue || 0)) return false;
      if ((nodeById.get(edge.source)?.depth ?? 9) > maxDepth) return false;
      if ((nodeById.get(edge.target)?.depth ?? 9) > maxDepth) return false;
      if (!q) return true;
      return edge.source.includes(q)
        || edge.target.includes(q)
        || edge.transactions.some(tx => String(tx.hash).toLowerCase().includes(q));
    });
    const visible = new Set();
    edges.forEach(edge => { visible.add(edge.source); visible.add(edge.target); });
    if (!q) network.nodes.filter(node => node.depth <= maxDepth).forEach(node => visible.add(node.id));
    return { nodes: network.nodes.filter(node => visible.has(node.id)), edges };
  }, [network, query, minValue, maxDepth]);

  const selectedNode = selected?.kind === 'node' ? network.nodes.find(node => node.id === selected.id) : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;

  useEffect(() => {
    if (mode !== 'map') return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let running = true;

    const draw = () => {
      if (!running) return;
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#02040c';
      ctx.fillRect(0, 0, width, height);

      const worldToScreen = node => ({
        x: width / 2 + pan.x + node.x * zoom,
        y: height / 2 + pan.y + node.y * zoom,
      });
      const points = new Map(filtered.nodes.map(node => [node.id, worldToScreen(node)]));
      const nodeById = new Map(network.nodes.map(node => [node.id, node]));
      const maxValue = Math.max(1, ...filtered.edges.map(edge => edge.totalValue));
      const edgeHits = [];

      for (const edge of filtered.edges) {
        const a = points.get(edge.source);
        const b = points.get(edge.target);
        if (!a || !b) continue;
        const sourceNode = nodeById.get(edge.source);
        const targetNode = nodeById.get(edge.target);
        const sameProminentCluster = sourceNode?.cluster === targetNode?.cluster && sourceNode?.cluster < 2;
        const active = selectedEdge?.id === edge.id || hovered?.kind === 'edge' && hovered.id === edge.id;
        const strength = Math.log10(edge.totalValue + 1) / Math.max(1, Math.log10(maxValue + 1));
        const color = active ? '#ffffff' : sameProminentCluster ? nodeColor(sourceNode) : '#42516a';
        const alpha = active ? 0.96 : sameProminentCluster ? 0.42 : 0.16;

        ctx.save();
        ctx.strokeStyle = color;
        ctx.globalAlpha = alpha;
        ctx.lineWidth = active ? 2.2 : 0.55 + strength * 1.15;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();

        if (active || zoom >= 1.65) drawArrow(ctx, a, b, active ? '#ffffff' : '#cbd5e1', active ? 0.96 : 0.72);
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      const nodeHits = [];
      for (const node of filtered.nodes) {
        const point = points.get(node.id);
        if (!point) continue;
        const radius = nodeRadius(node, zoom);
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hovered?.kind === 'node' && hovered.id === node.id;
        drawBubble(ctx, node, point, radius, isSelected, isHovered);

        if ((isSelected || isHovered) && zoom > 0.55) {
          ctx.save();
          ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
          ctx.fillStyle = '#f8fafc';
          ctx.globalAlpha = 0.94;
          ctx.fillText(short(node.id), point.x + radius + 7, point.y + 4);
          ctx.restore();
        }
        nodeHits.push({ id: node.id, x: point.x, y: point.y, r: radius + 6 });
      }

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      running = false;
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [filtered, network.nodes, zoom, pan, selectedNode?.id, selectedEdge?.id, hovered, mode]);

  function pointerPosition(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function hitAt(event) {
    const point = pointerPosition(event);
    const node = [...hitRef.current.nodes].reverse().find(hit => Math.hypot(point.x - hit.x, point.y - hit.y) <= hit.r);
    if (node) return { kind: 'node', id: node.id };
    const edge = [...hitRef.current.edges].reverse().find(hit => distanceToSegment(point.x, point.y, hit.ax, hit.ay, hit.bx, hit.by) <= 6);
    return edge ? { kind: 'edge', id: edge.id } : null;
  }

  function onPointerDown(event) {
    const hit = hitAt(event);
    if (hit) {
      setSelected(hit);
      return;
    }
    dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    if (dragRef.current) {
      setPan({
        x: dragRef.current.panX + event.clientX - dragRef.current.x,
        y: dragRef.current.panY + event.clientY - dragRef.current.y,
      });
      return;
    }
    setHovered(hitAt(event));
  }

  function onWheel(event) {
    event.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.14 : 0.88;
    const nextZoom = clamp(zoom * factor, 0.22, 4.8);
    const worldX = (px - rect.width / 2 - pan.x) / zoom;
    const worldY = (py - rect.height / 2 - pan.y) / zoom;
    setPan({
      x: px - rect.width / 2 - worldX * nextZoom,
      y: py - rect.height / 2 - worldY * nextZoom,
    });
    setZoom(nextZoom);
  }

  function resetView() {
    setZoom(0.72);
    setPan({ x: 0, y: 0 });
  }

  const relatedEdges = selectedNode
    ? network.edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
    : [];

  return <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[#02040c] shadow-2xl shadow-black/30">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-[#080b14] px-5 py-3">
      <div>
        <p className="eyebrow">Flow intelligence</p>
        <h3 className="mt-1 text-lg font-semibold text-white">Interactive fund-flow map</h3>
      </div>
      <div className="text-xs text-slate-500">{filtered.nodes.length} wallets · {filtered.edges.length} relationships</div>
    </div>

    <div className="relative bg-[#02040c]">
      <div className="absolute left-3 top-3 z-20 flex max-w-[calc(100%-24px)] flex-wrap gap-2 rounded-xl border border-slate-800/80 bg-[#0a0e18]/95 p-2 shadow-xl backdrop-blur">
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Wallet or tx hash" className="h-9 w-48 rounded-lg border border-slate-700 bg-[#111827] px-3 font-mono text-xs text-slate-200 outline-none focus:border-cyan-500/60" />
        <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} aria-label="Minimum transfer value" className="h-9 w-24 rounded-lg border border-slate-700 bg-[#111827] px-3 text-xs text-slate-200 outline-none" />
        <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="h-9 rounded-lg border border-slate-700 bg-[#111827] px-3 text-xs text-slate-200">
          <option value={1}>1 hop</option><option value={2}>2 hops</option><option value={3}>3 hops</option><option value={9}>All loaded</option>
        </select>
        <button type="button" onClick={() => setMode(mode === 'map' ? 'table' : 'map')} className="secondary-button h-9 text-xs">{mode === 'map' ? 'Table' : 'Map'}</button>
        <button type="button" onClick={resetView} className="secondary-button h-9 text-xs">Fit map</button>
      </div>

      {mode === 'map' ? <>
        <canvas
          ref={canvasRef}
          className="h-[700px] w-full touch-none cursor-grab active:cursor-grabbing"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHovered(null)}
          onPointerUp={() => { dragRef.current = null; }}
          onPointerCancel={() => { dragRef.current = null; }}
          onWheel={onWheel}
        />

        {!filtered.nodes.length && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">No loaded relationships match these filters.</div>}

        {(selectedNode || selectedEdge) && <div className="absolute left-4 top-20 z-20 w-[300px] rounded-xl border border-slate-700/80 bg-[#111522]/96 p-4 text-sm shadow-2xl backdrop-blur">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-[.24em] text-slate-500">{selectedNode ? 'Wallet' : 'Relationship'}</p>
              <p className="mt-1 break-all font-mono text-xs text-slate-200">{selectedNode ? selectedNode.id : `${short(selectedEdge.source)} → ${short(selectedEdge.target)}`}</p>
            </div>
            <button type="button" onClick={() => setSelected(null)} className="text-slate-500 hover:text-white">×</button>
          </div>

          {selectedNode && <>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-slate-900/80 p-2"><p className="font-semibold text-white">{selectedNode.txCount}</p><p className="text-[10px] text-slate-500">Tx</p></div>
              <div className="rounded-lg bg-slate-900/80 p-2"><p className="font-semibold text-white">{selectedNode.counterparties.size}</p><p className="text-[10px] text-slate-500">Addresses</p></div>
              <div className="rounded-lg bg-slate-900/80 p-2"><p className="font-semibold text-white">{selectedNode.depth}</p><p className="text-[10px] text-slate-500">Hop</p></div>
            </div>
            <div className="mt-3 space-y-2 text-xs text-slate-400">
              <div className="flex justify-between gap-3"><span>Observed IN</span><span className="font-mono text-slate-200">{selectedNode.incomingValue.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></div>
              <div className="flex justify-between gap-3"><span>Observed OUT</span><span className="font-mono text-slate-200">{selectedNode.outgoingValue.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></div>
            </div>
            <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-cyan-300 hover:underline">Open on Etherscan ↗</a>
            <div className="mt-3 max-h-36 space-y-1 overflow-auto pr-1">
              {relatedEdges.slice(0, 8).map(edge => <button key={edge.id} type="button" onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="w-full rounded-md bg-slate-900/70 px-2 py-2 text-left text-[11px] text-slate-400 hover:bg-slate-800"><span className="font-mono text-slate-200">{short(edge.source)} → {short(edge.target)}</span><span className="mt-1 block">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 5 })} {edge.asset}</span></button>)}
            </div>
          </>}

          {selectedEdge && <>
            <div className="rounded-lg bg-slate-900/80 p-3">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">Observed value</p>
              <p className="mt-1 text-lg font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p>
              <p className="mt-1 text-[11px] text-slate-500">{selectedEdge.txCount} loaded transaction{selectedEdge.txCount === 1 ? '' : 's'}</p>
            </div>
            <div className="mt-3 max-h-48 space-y-1 overflow-auto pr-1">
              {selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-md bg-slate-900/70 px-2 py-2 text-left hover:bg-slate-800"><span className="block font-mono text-[11px] text-cyan-300">{short(tx.hash)}</span><span className="mt-1 block text-[10px] text-slate-500">{tx.value} {tx.asset || ''} · {tx.category || 'transfer'}</span></button>)}
            </div>
          </>}
        </div>}

        <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-slate-800/80 bg-[#090d17]/90 px-3 py-2 text-[11px] text-slate-500">Drag to pan · wheel to zoom · click bubble or link</div>
      </> : <div className="max-h-[700px] overflow-auto pt-16">
        <table className="min-w-full text-left text-xs">
          <thead className="sticky top-0 border-b border-slate-800 bg-[#080b14] text-slate-500"><tr><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Observed value</th><th className="px-4 py-3">Tx count</th><th className="px-4 py-3">Evidence</th></tr></thead>
          <tbody>{filtered.edges.map(edge => <tr key={edge.id} className="border-b border-slate-900 text-slate-300"><td className="px-4 py-3 font-mono">{short(edge.source)}</td><td className="px-4 py-3 font-mono">{short(edge.target)}</td><td className="px-4 py-3">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {edge.asset}</td><td className="px-4 py-3">{edge.txCount}</td><td className="px-4 py-3"><button type="button" onClick={() => { setSelected({ kind: 'edge', id: edge.id }); setMode('map'); }} className="text-cyan-300 hover:underline">Inspect</button></td></tr>)}</tbody>
        </table>
      </div>}
    </div>

    <div className="border-t border-amber-500/10 bg-amber-400/[0.02] px-4 py-3 text-[11px] leading-5 text-amber-200/70">Observed loaded ChainScope evidence only. Cluster placement visualizes observed relationships and does not prove common ownership or complete fund provenance.</div>
  </section>;
}
