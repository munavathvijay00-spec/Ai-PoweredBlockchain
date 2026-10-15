import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 6)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const COLORS = {
  root: '#22c98b',
  incoming: '#0dd9f5',
  outgoing: '#f10da9',
  both: '#8b5cf6',
  second: '#43516a',
  edge: '#46546d',
};

function numberValue(value) {
  const parsed = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function aggregate(transactions, root) {
  const rootId = norm(root);
  const nodes = new Map();
  const edges = new Map();
  const adjacency = new Map();

  const ensure = id => {
    const key = norm(id);
    if (!key) return null;
    if (!nodes.has(key)) {
      nodes.set(key, {
        id: key,
        txCount: 0,
        incoming: 0,
        outgoing: 0,
        counterparties: new Set(),
        inByAsset: {},
        outByAsset: {},
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
    const asset = tx.asset || 'ETH';
    const value = numberValue(tx.value);
    const key = `${source}|${target}|${asset}`;

    if (!edges.has(key)) {
      edges.set(key, { id: key, source, target, asset, totalValue: 0, txCount: 0, transactions: [], maxRisk: null });
    }
    const edge = edges.get(key);
    edge.totalValue += value;
    edge.txCount += 1;
    edge.transactions.push(tx);
    if (tx.risk_score != null) edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);

    const from = ensure(source);
    const to = ensure(target);
    from.txCount += 1;
    from.outgoing += 1;
    from.counterparties.add(target);
    from.outByAsset[asset] = (from.outByAsset[asset] || 0) + value;
    to.txCount += 1;
    to.incoming += 1;
    to.counterparties.add(source);
    to.inByAsset[asset] = (to.inByAsset[asset] || 0) + value;
    if (tx.risk_score != null) {
      const risk = Number(tx.risk_score) || 0;
      from.maxRisk = Math.max(from.maxRisk ?? 0, risk);
      to.maxRisk = Math.max(to.maxRisk ?? 0, risk);
    }
    adjacency.get(source).add(target);
    adjacency.get(target).add(source);
  }

  const depth = new Map();
  const parent = new Map();
  if (rootId && nodes.has(rootId)) {
    depth.set(rootId, 0);
    const queue = [rootId];
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      for (const neighbor of adjacency.get(current) || []) {
        if (depth.has(neighbor)) continue;
        depth.set(neighbor, (depth.get(current) || 0) + 1);
        parent.set(neighbor, current);
        queue.push(neighbor);
      }
    }
  }

  const rootEdges = [...edges.values()].filter(edge => edge.source === rootId || edge.target === rootId);
  const incomingRoot = rootEdges.filter(edge => edge.target === rootId).map(edge => edge.source);
  const outgoingRoot = rootEdges.filter(edge => edge.source === rootId).map(edge => edge.target);
  const incomingSet = new Set(incomingRoot);
  const outgoingSet = new Set(outgoingRoot);

  const positioned = [];
  const rootNode = nodes.get(rootId);
  if (rootNode) positioned.push({ ...rootNode, x: 0, y: 0, depth: 0, direction: 'root', isRoot: true });

  const direct = [...new Set([...incomingRoot, ...outgoingRoot])]
    .map(id => nodes.get(id))
    .filter(Boolean)
    .sort((a, b) => b.txCount - a.txCount);

  const left = direct.filter(node => incomingSet.has(node.id) && !outgoingSet.has(node.id));
  const right = direct.filter(node => outgoingSet.has(node.id) && !incomingSet.has(node.id));
  const both = direct.filter(node => incomingSet.has(node.id) && outgoingSet.has(node.id));

  function placeSide(list, side, direction) {
    const count = Math.max(1, list.length);
    list.forEach((node, index) => {
      const row = index - (count - 1) / 2;
      const y = row * 66;
      const x = side * (230 + Math.abs(row) * 8);
      positioned.push({ ...node, x, y, depth: 1, direction, isRoot: false });
    });
  }

  placeSide(left, -1, 'incoming');
  placeSide(right, 1, 'outgoing');
  both.forEach((node, index) => {
    const side = index % 2 === 0 ? -1 : 1;
    const row = Math.floor(index / 2);
    positioned.push({ ...node, x: side * (170 + row * 32), y: -210 - row * 60, depth: 1, direction: 'both', isRoot: false });
  });

  const positionedIds = new Set(positioned.map(node => node.id));
  for (const node of nodes.values()) {
    if (positionedIds.has(node.id)) continue;
    const d = depth.get(node.id) ?? 2;
    const parentId = parent.get(node.id);
    const parentNode = positioned.find(item => item.id === parentId);
    const base = parentNode || { x: 0, y: 0 };
    const angle = ((node.id.charCodeAt(node.id.length - 1) || 0) / 255) * Math.PI * 2;
    const radius = 76 + Math.min(72, d * 22);
    positioned.push({
      ...node,
      x: base.x + Math.cos(angle) * radius,
      y: base.y + Math.sin(angle) * radius,
      depth: d,
      direction: 'second',
      isRoot: false,
    });
  }

  return { nodes: positioned, edges: [...edges.values()], adjacency, root: rootId };
}

function relevance(edge, root, nodeById) {
  const touchesRoot = edge.source === root || edge.target === root ? 100000 : 0;
  const activity = (nodeById.get(edge.source)?.txCount || 0) + (nodeById.get(edge.target)?.txCount || 0);
  return touchesRoot + edge.txCount * 100 + Math.log10(edge.totalValue + 1) * 20 + activity;
}

function nodeColor(node) {
  if (node.isRoot) return COLORS.root;
  return COLORS[node.direction] || COLORS.second;
}

function sphere(ctx, x, y, radius, color, state = 'default') {
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur = state === 'selected' ? 10 : state === 'hovered' ? 6 : 2;
  const gradient = ctx.createRadialGradient(x - radius * .3, y - radius * .34, radius * .1, x, y, radius);
  gradient.addColorStop(0, '#e2e8f0');
  gradient.addColorStop(.16, color);
  gradient.addColorStop(.58, color);
  gradient.addColorStop(1, '#08101d');
  ctx.fillStyle = gradient;
  ctx.globalAlpha = state === 'dimmed' ? .11 : .88;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.strokeStyle = state === 'selected' ? '#ffffff' : color;
  ctx.lineWidth = state === 'selected' ? 2 : 1;
  ctx.stroke();
  ctx.restore();
}

function assetRows(node) {
  const assets = new Set([...Object.keys(node.inByAsset), ...Object.keys(node.outByAsset)]);
  return [...assets].map(asset => ({ asset, incoming: node.inByAsset[asset] || 0, outgoing: node.outByAsset[asset] || 0 }));
}

export default function AccurateSuperBubbleGraph({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [zoom, setZoom] = useState(.92);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [mode, setMode] = useState('focused');
  const [maxDepth, setMaxDepth] = useState(2);
  const [minValue, setMinValue] = useState(0);
  const [query, setQuery] = useState('');
  const [balanceCache, setBalanceCache] = useState({});
  const [balanceLoading, setBalanceLoading] = useState(false);

  const network = useMemo(() => aggregate(transactions, root), [transactions, root]);
  const nodeById = useMemo(() => new Map(network.nodes.map(node => [node.id, node])), [network.nodes]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let edges = network.edges.filter(edge => {
      if (edge.totalValue < Number(minValue || 0)) return false;
      const a = nodeById.get(edge.source);
      const b = nodeById.get(edge.target);
      if ((a?.depth ?? 9) > maxDepth || (b?.depth ?? 9) > maxDepth) return false;
      if (!q) return true;
      return edge.source.includes(q) || edge.target.includes(q) || edge.transactions.some(tx => String(tx.hash).toLowerCase().includes(q));
    });

    if (mode === 'focused' && !q) {
      edges = [...edges]
        .sort((a, b) => relevance(b, network.root, nodeById) - relevance(a, network.root, nodeById))
        .slice(0, 42);
    }

    const ids = new Set();
    edges.forEach(edge => { ids.add(edge.source); ids.add(edge.target); });
    if (network.root) ids.add(network.root);
    return { edges, nodes: network.nodes.filter(node => ids.has(node.id)) };
  }, [network, nodeById, mode, maxDepth, minValue, query]);

  const selectedNode = selected?.kind === 'node' ? nodeById.get(selected.id) : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;
  const connected = useMemo(() => selectedNode ? new Set(network.adjacency.get(selectedNode.id) || []) : new Set(), [selectedNode, network.adjacency]);
  const balance = selectedNode ? balanceCache[selectedNode.id] : null;

  useEffect(() => {
    if (!selectedNode || balanceCache[selectedNode.id]) return;
    let cancelled = false;
    setBalanceLoading(true);
    api.getWalletBalance(selectedNode.id)
      .then(data => {
        if (!cancelled) setBalanceCache(previous => ({ ...previous, [selectedNode.id]: { status: 'ready', ...data } }));
      })
      .catch(error => {
        if (!cancelled) setBalanceCache(previous => ({ ...previous, [selectedNode.id]: { status: 'error', message: error.message || 'Balance unavailable' } }));
      })
      .finally(() => { if (!cancelled) setBalanceLoading(false); });
    return () => { cancelled = true; };
  }, [selectedNode, balanceCache]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let frame;

    const draw = () => {
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
      ctx.fillStyle = '#070b12';
      ctx.fillRect(0, 0, width, height);

      const projected = new Map();
      visible.nodes.forEach(node => projected.set(node.id, { x: width / 2 + pan.x + node.x * zoom, y: height / 2 + pan.y + node.y * zoom }));

      const edgeHits = [];
      for (const edge of visible.edges) {
        const a = projected.get(edge.source);
        const b = projected.get(edge.target);
        if (!a || !b) continue;
        const active = selectedEdge?.id === edge.id || selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
        const dimmed = selectedNode && !active;
        ctx.save();
        ctx.strokeStyle = active ? '#94a3b8' : COLORS.edge;
        ctx.globalAlpha = active ? .62 : dimmed ? .025 : .11;
        ctx.lineWidth = active ? 1.5 : .7;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      const nodeHits = [];
      for (const node of visible.nodes) {
        const point = projected.get(node.id);
        if (!point) continue;
        const selectedNow = selectedNode?.id === node.id;
        const hoveredNow = hovered?.kind === 'node' && hovered.id === node.id;
        const dimmed = selectedNode && !selectedNow && !connected.has(node.id);
        const base = node.isRoot ? 22 : 9 + Math.min(12, Math.log2(node.txCount + node.counterparties.size + 2) * 2.8);
        const radius = clamp(base * Math.sqrt(zoom), node.isRoot ? 14 : 6, node.isRoot ? 34 : 24) * (selectedNow ? 1.12 : hoveredNow ? 1.05 : 1);
        sphere(ctx, point.x, point.y, radius, nodeColor(node), selectedNow ? 'selected' : hoveredNow ? 'hovered' : dimmed ? 'dimmed' : 'default');
        if (selectedNow || hoveredNow || node.isRoot) {
          ctx.save();
          ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
          ctx.fillStyle = '#cbd5e1';
          ctx.globalAlpha = dimmed ? .18 : .82;
          ctx.fillText(short(node.id), point.x + radius + 6, point.y + 3);
          ctx.restore();
        }
        nodeHits.push({ id: node.id, x: point.x, y: point.y, r: radius + 6 });
      }

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [visible, selectedNode, selectedEdge, connected, hovered, zoom, pan]);

  function pointer(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function distanceToEdge(p, edge) {
    const dx = edge.bx - edge.ax;
    const dy = edge.by - edge.ay;
    const len = dx * dx + dy * dy || 1;
    const t = clamp(((p.x - edge.ax) * dx + (p.y - edge.ay) * dy) / len, 0, 1);
    return Math.hypot(p.x - (edge.ax + t * dx), p.y - (edge.ay + t * dy));
  }

  function hitAt(event) {
    const p = pointer(event);
    const node = [...hitRef.current.nodes].reverse().find(item => Math.hypot(p.x - item.x, p.y - item.y) <= item.r);
    if (node) return { kind: 'node', id: node.id };
    const edge = [...hitRef.current.edges].reverse().find(item => distanceToEdge(p, item) <= 6);
    return edge ? { kind: 'edge', id: edge.id } : null;
  }

  function onPointerDown(event) {
    const hit = hitAt(event);
    if (hit) {
      setSelected(hit);
      return;
    }
    setSelected(null);
    dragRef.current = { x: event.clientX, y: event.clientY, pan };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    if (dragRef.current) {
      setPan({ x: dragRef.current.pan.x + event.clientX - dragRef.current.x, y: dragRef.current.pan.y + event.clientY - dragRef.current.y });
      return;
    }
    setHovered(hitAt(event));
  }

  function onWheel(event) {
    event.preventDefault();
    setZoom(value => clamp(value * (event.deltaY < 0 ? 1.1 : .9), .48, 2.2));
  }

  function retryBalance() {
    if (!selectedNode) return;
    setBalanceCache(previous => {
      const next = { ...previous };
      delete next[selectedNode.id];
      return next;
    });
  }

  const hiddenNodes = Math.max(0, network.nodes.length - visible.nodes.length);
  const hiddenEdges = Math.max(0, network.edges.length - visible.edges.length);
  const rows = selectedNode ? assetRows(selectedNode).slice(0, 2) : [];

  return <section className="overflow-hidden rounded-xl border border-white/[0.07] bg-[#070b12]">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
      <div><p className="text-[10px] uppercase tracking-[.2em] text-slate-500">Wallet flow</p><h3 className="mt-1 text-sm font-medium text-slate-100">Investigation map</h3></div>
      <div className="text-[11px] text-slate-500">{visible.nodes.length} wallets · {visible.edges.length} links</div>
    </div>

    <div className="flex flex-wrap gap-2 border-b border-white/[0.05] px-3 py-2">
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Address or tx hash" className="h-8 min-w-[210px] flex-1 rounded-md border border-slate-800 bg-[#0d121b] px-3 font-mono text-[11px] text-slate-200 outline-none" />
      <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} className="h-8 w-24 rounded-md border border-slate-800 bg-[#0d121b] px-2 text-[11px] text-slate-200 outline-none" title="Minimum observed transfer value" />
      <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="h-8 rounded-md border border-slate-800 bg-[#0d121b] px-2 text-[11px] text-slate-200"><option value={1}>1 hop</option><option value={2}>2 hops</option><option value={3}>3 hops</option><option value={9}>All hops</option></select>
      <button type="button" onClick={() => setMode(value => value === 'focused' ? 'all' : 'focused')} className="h-8 rounded-md border border-slate-800 bg-[#101620] px-3 text-[11px] text-slate-300">{mode === 'focused' ? 'Show all' : 'Focus'}</button>
      <button type="button" onClick={() => { setZoom(.92); setPan({ x: 0, y: 0 }); setSelected(null); }} className="h-8 rounded-md border border-slate-800 bg-[#101620] px-3 text-[11px] text-slate-300">Reset</button>
    </div>

    <div className="relative">
      <canvas ref={canvasRef} className="h-[560px] w-full touch-none cursor-grab active:cursor-grabbing" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerLeave={() => setHovered(null)} onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }} onWheel={onWheel} />

      {selectedNode && <div className="absolute left-3 top-3 z-20 w-[290px] max-w-[calc(100%-24px)] rounded-lg border border-white/[0.08] bg-[#0d121b]/97 p-3 shadow-xl backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><p className="text-[9px] uppercase tracking-[.18em] text-slate-500">Wallet</p><p className="mt-1 truncate font-mono text-[11px] text-slate-200" title={selectedNode.id}>{selectedNode.id}</p></div>
          <button type="button" onClick={() => setSelected(null)} className="text-slate-500 hover:text-white">×</button>
        </div>

        <div className="mt-3 border-y border-white/[0.06] py-3">
          <div className="flex items-center justify-between gap-3"><span className="text-[10px] uppercase tracking-wider text-slate-500">ETH balance</span>{balance?.status === 'ready' && <span className="text-[9px] text-emerald-300">mainnet · verified</span>}</div>
          {balanceLoading && !balance && <p className="mt-2 text-sm text-slate-400">Loading…</p>}
          {balance?.status === 'ready' && <><p className="mt-1 text-2xl font-semibold tracking-tight text-white">{Number(balance.balance_eth).toLocaleString(undefined, { maximumFractionDigits: 8 })} ETH</p><p className="mt-1 text-[9px] text-slate-600">Block {Number(balance.block_number).toLocaleString()}</p></>}
          {balance?.status === 'error' && <div className="mt-2"><p className="text-[11px] text-rose-300">Balance unavailable</p><p className="mt-1 text-[9px] text-slate-600">{balance.message}</p><button type="button" onClick={retryBalance} className="mt-2 text-[10px] text-cyan-300 hover:underline">Retry</button></div>}
        </div>

        <p className="mt-3 text-[11px] text-slate-400">{selectedNode.txCount} transfers · {selectedNode.counterparties.size} counterpart{selectedNode.counterparties.size === 1 ? 'y' : 'ies'} · hop {selectedNode.depth}</p>

        {rows.length > 0 && <div className="mt-3 space-y-1.5">{rows.map(row => <div key={row.asset} className="flex items-center justify-between gap-2 rounded-md bg-[#090e16] px-2.5 py-2 text-[10px]"><span className="font-medium text-slate-300">{row.asset}</span><span className="text-slate-500">IN {row.incoming.toLocaleString(undefined, { maximumFractionDigits: 4 })} · OUT {row.outgoing.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span></div>)}</div>}

        <div className="mt-3 flex items-center justify-between"><span className="text-[10px] text-slate-600">Risk {selectedNode.maxRisk == null ? 'not assessed' : selectedNode.maxRisk}</span><a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="text-[10px] text-cyan-300 hover:underline">Etherscan ↗</a></div>
      </div>}

      {selectedEdge && <div className="absolute left-3 top-3 z-20 w-[290px] max-w-[calc(100%-24px)] rounded-lg border border-white/[0.08] bg-[#0d121b]/97 p-3 shadow-xl backdrop-blur"><div className="flex items-start justify-between gap-3"><div><p className="text-[9px] uppercase tracking-[.18em] text-slate-500">Relationship</p><p className="mt-1 font-mono text-[11px] text-slate-200">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div><button type="button" onClick={() => setSelected(null)} className="text-slate-500 hover:text-white">×</button></div><p className="mt-3 text-xl font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p><p className="mt-1 text-[10px] text-slate-600">{selectedEdge.txCount} loaded transaction{selectedEdge.txCount === 1 ? '' : 's'}</p><div className="mt-3 max-h-32 space-y-1 overflow-auto">{selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-md bg-[#090e16] px-2.5 py-2 text-left"><span className="font-mono text-[10px] text-cyan-300">{short(tx.hash)}</span><span className="ml-2 text-[9px] text-slate-600">{tx.value} {tx.asset || ''}</span></button>)}</div></div>}

      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-[#0b1018]/90 px-2.5 py-1.5 text-[10px] text-slate-600">Drag · wheel zoom · click wallet</div>
    </div>

    {(hiddenNodes > 0 || hiddenEdges > 0) && <div className="border-t border-white/[0.05] px-4 py-2 text-[10px] text-slate-600">Focused view hides {hiddenNodes} wallet{hiddenNodes === 1 ? '' : 's'} and {hiddenEdges} link{hiddenEdges === 1 ? '' : 's'} from the loaded evidence. Use “Show all” when needed.</div>}
  </section>;
}
