import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-5)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const PALETTE = ['#ec4899', '#22d3ee', '#a855f7', '#60a5fa', '#14b8a6', '#f97316'];
const MUTED = '#203047';

function numericValue(value) {
  const parsed = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function edgeKey(source, target, asset) {
  return `${source}|${target}|${asset}`;
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
    }
    if (!adjacency.has(key)) adjacency.set(key, new Set());
    return nodes.get(key);
  };

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;

    const from = ensureNode(source);
    const to = ensureNode(target);
    const value = numericValue(tx.value);
    const asset = tx.asset || 'ETH';
    const key = edgeKey(source, target, asset);

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
  const owner = new Map();
  if (rootId && nodes.has(rootId)) {
    depth.set(rootId, 0);
    owner.set(rootId, rootId);
    const queue = [rootId];
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      const currentDepth = depth.get(current) ?? 0;
      for (const neighbor of adjacency.get(current) || []) {
        if (!depth.has(neighbor)) {
          depth.set(neighbor, currentDepth + 1);
          owner.set(neighbor, current === rootId ? neighbor : owner.get(current));
          queue.push(neighbor);
        }
      }
    }
  }

  const firstHop = [...(adjacency.get(rootId) || [])]
    .sort((a, b) => (nodes.get(b)?.txCount || 0) - (nodes.get(a)?.txCount || 0));
  const clusterIds = new Map(firstHop.map((id, index) => [id, index]));

  const groups = new Map();
  for (const node of nodes.values()) {
    const key = node.id === rootId ? 'root' : (owner.get(node.id) || node.id);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }

  const centers = new Map();
  const keys = [...groups.keys()].filter(key => key !== 'root');
  keys.forEach((key, index) => {
    const ring = Math.floor(index / 7);
    const within = index % 7;
    const count = Math.min(7, keys.length - ring * 7);
    const angle = (within / Math.max(1, count)) * Math.PI * 2 + ring * 0.53;
    const radius = 245 + ring * 210;
    centers.set(key, {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius * 0.72,
    });
  });

  const positioned = [];
  for (const [key, group] of groups.entries()) {
    if (key === 'root') {
      const node = group[0];
      positioned.push({ ...node, x: 0, y: 0, depth: 0, cluster: -1, isRoot: true });
      continue;
    }

    const center = centers.get(key) || { x: 0, y: 0 };
    const clusterIndex = clusterIds.get(key) ?? [...clusterIds.keys()].length + keys.indexOf(key);
    const ordered = [...group].sort((a, b) => b.txCount - a.txCount);

    ordered.forEach((node, index) => {
      if (index === 0) {
        positioned.push({
          ...node,
          x: center.x,
          y: center.y,
          depth: depth.get(node.id) ?? 1,
          cluster: clusterIndex,
          isRoot: false,
        });
        return;
      }
      const orbit = 58 + 31 * Math.sqrt(index);
      const angle = index * 2.399963229728653 + clusterIndex * 0.41;
      positioned.push({
        ...node,
        x: center.x + Math.cos(angle) * orbit,
        y: center.y + Math.sin(angle) * orbit,
        depth: depth.get(node.id) ?? 2,
        cluster: clusterIndex,
        isRoot: false,
      });
    });
  }

  if (!positioned.length) return { nodes: [], edges: [], root: rootId };
  return { nodes: positioned, edges: [...edges.values()], root: rootId };
}

function nodeColor(node) {
  if (node.isRoot) return '#22d3ee';
  if (node.maxRisk != null && node.maxRisk >= 70) return '#f43f5e';
  if (node.maxRisk != null && node.maxRisk >= 40) return '#f59e0b';
  if (node.cluster >= 0 && node.cluster < 3) return PALETTE[node.cluster % PALETTE.length];
  return MUTED;
}

function drawBubble(ctx, node, point, selected, hovered) {
  const color = nodeColor(node);
  const importance = Math.log2(node.txCount + node.counterparties.size + 2);
  const base = node.isRoot ? 21 : 8 + importance * 2.8;
  const radius = clamp(base * point.scale, 5, node.isRoot ? 42 : 34);
  const active = selected || hovered;
  const muted = color === MUTED;

  ctx.save();
  ctx.shadowColor = muted ? 'transparent' : color;
  ctx.shadowBlur = active ? 20 : muted ? 0 : 9;
  ctx.globalAlpha = muted ? 0.36 : active ? 1 : 0.92;
  ctx.fillStyle = muted ? 'rgba(19,31,47,.72)' : `${color}24`;
  ctx.strokeStyle = active ? '#ffffff' : color;
  ctx.lineWidth = active ? 2.4 : muted ? 1 : 2;
  ctx.beginPath();
  ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  if (!muted) {
    ctx.globalAlpha = active ? 0.94 : 0.52;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(point.x, point.y, Math.max(2.2, radius * 0.22), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
  return radius;
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
  const [zoom, setZoom] = useState(0.88);
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
    let active = true;

    const draw = () => {
      if (!active) return;
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
      ctx.fillStyle = '#030712';
      ctx.fillRect(0, 0, width, height);

      const worldToScreen = node => ({
        x: width / 2 + pan.x + node.x * zoom,
        y: height / 2 + pan.y + node.y * zoom,
        scale: zoom,
      });
      const points = new Map(filtered.nodes.map(node => [node.id, worldToScreen(node)]));
      const edgeHits = [];
      const maxValue = Math.max(1, ...filtered.edges.map(edge => edge.totalValue));

      for (const edge of filtered.edges) {
        const a = points.get(edge.source);
        const b = points.get(edge.target);
        if (!a || !b) continue;
        const activeEdge = selectedEdge?.id === edge.id || hovered?.kind === 'edge' && hovered.id === edge.id;
        const sourceNode = network.nodes.find(node => node.id === edge.source);
        const targetNode = network.nodes.find(node => node.id === edge.target);
        const sameCluster = sourceNode?.cluster === targetNode?.cluster;
        const strength = Math.log10(edge.totalValue + 1) / Math.max(1, Math.log10(maxValue + 1));

        ctx.save();
        ctx.strokeStyle = activeEdge ? '#ffffff' : sameCluster && sourceNode?.cluster < 3 ? nodeColor(sourceNode) : '#38506f';
        ctx.globalAlpha = activeEdge ? 0.95 : sameCluster ? 0.34 : 0.17;
        ctx.lineWidth = activeEdge ? 2.2 : 0.65 + strength * 1.2;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      const nodeHits = [];
      for (const node of filtered.nodes) {
        const point = points.get(node.id);
        if (!point) continue;
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hovered?.kind === 'node' && hovered.id === node.id;
        const radius = drawBubble(ctx, node, point, isSelected, isHovered);

        if ((isSelected || isHovered || (node.isRoot && zoom > 0.7)) && zoom > 0.45) {
          ctx.save();
          ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
          ctx.fillStyle = '#e2e8f0';
          ctx.globalAlpha = 0.9;
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
      active = false;
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [filtered, zoom, pan, selectedNode?.id, selectedEdge?.id, hovered, mode, network.nodes]);

  function pointerPosition(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function hitAt(event) {
    const point = pointerPosition(event);
    const node = [...hitRef.current.nodes]
      .reverse()
      .find(hit => Math.hypot(point.x - hit.x, point.y - hit.y) <= hit.r);
    if (node) return { kind: 'node', id: node.id };
    const edge = [...hitRef.current.edges]
      .reverse()
      .find(hit => distanceToSegment(point.x, point.y, hit.ax, hit.ay, hit.bx, hit.by) <= 6);
    return edge ? { kind: 'edge', id: edge.id } : null;
  }

  function pointerDown(event) {
    const hit = hitAt(event);
    if (hit) {
      setSelected(hit);
      return;
    }
    dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function pointerMove(event) {
    if (dragRef.current) {
      setPan({
        x: dragRef.current.panX + event.clientX - dragRef.current.x,
        y: dragRef.current.panY + event.clientY - dragRef.current.y,
      });
      return;
    }
    setHovered(hitAt(event));
  }

  function wheel(event) {
    event.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const previous = zoom;
    const next = clamp(previous * (event.deltaY < 0 ? 1.13 : 0.885), 0.24, 4.5);
    if (next === previous) return;
    const cx = rect.width / 2 + pan.x;
    const cy = rect.height / 2 + pan.y;
    const ratio = next / previous;
    setPan({
      x: pan.x + (mouseX - cx) * (1 - ratio),
      y: pan.y + (mouseY - cy) * (1 - ratio),
    });
    setZoom(next);
  }

  const relatedEdges = selectedNode
    ? network.edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
    : [];

  return <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[#030712] shadow-2xl shadow-black/30">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
      <div>
        <p className="eyebrow">Fund-flow intelligence</p>
        <h3 className="mt-1 text-lg font-semibold text-white">Interactive wallet bubble map</h3>
      </div>
      <div className="text-xs text-slate-400">{filtered.nodes.length} wallets · {filtered.edges.length} relationships</div>
    </div>

    <div className="grid gap-3 border-b border-slate-800 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_160px_150px_auto]">
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Wallet or transaction hash…" className="soft-input font-mono text-xs" />
      <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} className="soft-input text-xs" aria-label="Minimum transfer value" />
      <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="soft-input text-xs" aria-label="Maximum hop depth">
        <option value={1}>1 hop</option>
        <option value={2}>2 hops</option>
        <option value={3}>3 hops</option>
        <option value={9}>All loaded</option>
      </select>
      <div className="flex gap-2">
        <button type="button" onClick={() => setMode(mode === 'map' ? 'table' : 'map')} className="secondary-button text-xs">{mode === 'map' ? 'Table' : 'Bubble map'}</button>
        <button type="button" onClick={() => { setZoom(0.88); setPan({ x: 0, y: 0 }); }} className="secondary-button text-xs">Reset</button>
      </div>
    </div>

    {mode === 'map' ? <div className="grid lg:grid-cols-[minmax(0,1fr)_330px]">
      <div className="relative min-h-[660px] bg-[#030712]">
        <div className="absolute left-3 top-3 z-10 flex gap-2">
          <button type="button" onClick={() => setZoom(value => clamp(value * 1.2, 0.24, 4.5))} className="secondary-button px-3 py-1.5 text-xs">+</button>
          <button type="button" onClick={() => setZoom(value => clamp(value / 1.2, 0.24, 4.5))} className="secondary-button px-3 py-1.5 text-xs">−</button>
        </div>
        <canvas
          ref={canvasRef}
          className="h-[660px] w-full touch-none cursor-grab active:cursor-grabbing"
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerLeave={() => setHovered(null)}
          onPointerUp={() => { dragRef.current = null; }}
          onPointerCancel={() => { dragRef.current = null; }}
          onWheel={wheel}
        />
        {!filtered.nodes.length && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">No loaded relationships match these filters.</div>}
        <div className="pointer-events-none absolute bottom-3 left-4 rounded-full border border-slate-800 bg-slate-950/85 px-3 py-1.5 text-[11px] text-slate-400">Drag to pan · wheel to zoom · click a bubble or link</div>
      </div>

      <aside className="border-t border-slate-800 bg-[#050916] p-5 lg:border-l lg:border-t-0">
        <p className="eyebrow">Investigation details</p>
        {!selected && <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/45 p-4 text-sm leading-6 text-slate-400">Select a wallet bubble or relationship. Bright clusters show connected communities in the currently loaded evidence. Faint wallets remain visible without dominating the map.</div>}

        {selectedNode && <div className="mt-4 space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="mb-3 flex items-center gap-3">
              <span className="h-4 w-4 rounded-full border-2" style={{ borderColor: nodeColor(selectedNode), backgroundColor: `${nodeColor(selectedNode)}22` }} />
              <div><p className="text-xs text-slate-500">Wallet</p><p className="font-mono text-xs text-slate-200">{short(selectedNode.id)}</p></div>
            </div>
            <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="break-all font-mono text-[11px] text-cyan-300 hover:underline">{selectedNode.id} ↗</a>
          </div>

          <div className="grid grid-cols-2 gap-2 text-center text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-900/45 p-3"><p className="text-lg font-semibold text-white">{selectedNode.incoming}</p><p className="text-slate-500">Incoming</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/45 p-3"><p className="text-lg font-semibold text-white">{selectedNode.outgoing}</p><p className="text-slate-500">Outgoing</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/45 p-3"><p className="text-lg font-semibold text-white">{selectedNode.counterparties.size}</p><p className="text-slate-500">Neighbors</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/45 p-3"><p className="text-lg font-semibold text-white">{selectedNode.depth}</p><p className="text-slate-500">Hop</p></div>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-slate-300">Connected relationships</p>
            <div className="max-h-64 space-y-2 overflow-auto pr-1">
              {relatedEdges.slice(0, 14).map(edge => <button key={edge.id} type="button" onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="w-full rounded-lg border border-slate-800 bg-slate-900/45 p-2 text-left text-[11px] text-slate-400 hover:border-fuchsia-500/40"><span className="font-mono text-slate-300">{short(edge.source)} → {short(edge.target)}</span><span className="mt-1 block">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 6 })} {edge.asset} · {edge.txCount} tx</span></button>)}
            </div>
          </div>
        </div>}

        {selectedEdge && <div className="mt-4 space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <p className="text-xs text-slate-500">Relationship</p>
            <p className="mt-2 font-mono text-xs text-slate-200">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p>
            <p className="mt-3 text-xl font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p>
            <p className="mt-1 text-xs text-slate-500">{selectedEdge.txCount} loaded transaction{selectedEdge.txCount === 1 ? '' : 's'}</p>
          </div>
          <div>
            <p className="mb-2 text-xs font-medium text-slate-300">Evidence transactions</p>
            <div className="max-h-72 space-y-2 overflow-auto pr-1">
              {selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-lg border border-slate-800 bg-slate-900/45 p-2 text-left hover:border-cyan-500/40"><span className="block font-mono text-[11px] text-cyan-300">{short(tx.hash)}</span><span className="mt-1 block text-[11px] text-slate-500">{tx.value} {tx.asset || ''} · {tx.category || 'transfer'}</span></button>)}
            </div>
          </div>
        </div>}
      </aside>
    </div> : <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="border-b border-slate-800 bg-slate-950 text-slate-500"><tr><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Observed value</th><th className="px-4 py-3">Tx count</th><th className="px-4 py-3">Evidence</th></tr></thead>
        <tbody>{filtered.edges.map(edge => <tr key={edge.id} className="border-b border-slate-900 text-slate-300"><td className="px-4 py-3 font-mono">{short(edge.source)}</td><td className="px-4 py-3 font-mono">{short(edge.target)}</td><td className="px-4 py-3">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {edge.asset}</td><td className="px-4 py-3">{edge.txCount}</td><td className="px-4 py-3"><button type="button" onClick={() => { setSelected({ kind: 'edge', id: edge.id }); setMode('map'); }} className="text-cyan-300 hover:underline">Inspect</button></td></tr>)}</tbody>
      </table>
    </div>}

    <div className="border-t border-amber-500/10 bg-amber-400/[0.025] px-4 py-3 text-[11px] leading-5 text-amber-200/80">Observed loaded ChainScope evidence only. Cluster placement is a visualization of currently observed relationships, not proof of common ownership or complete fund provenance.</div>
  </section>;
}
