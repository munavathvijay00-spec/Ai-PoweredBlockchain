import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';

const norm = v => (v || '').toLowerCase();
const short = v => v ? `${v.slice(0, 6)}…${v.slice(-4)}` : '—';
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const valueOf = v => {
  const n = Number.parseFloat(String(v ?? '').replace(/,/g, ''));
  return Number.isFinite(n) ? n : 0;
};

function hash01(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

function buildNetwork(transactions, root) {
  const rootId = norm(root);
  const nodes = new Map();
  const edges = new Map();
  const adjacency = new Map();

  const ensure = id => {
    const key = norm(id);
    if (!key) return null;
    if (!nodes.has(key)) {
      nodes.set(key, { id: key, txCount: 0, incoming: 0, outgoing: 0, counterparties: new Set(), inByAsset: {}, outByAsset: {}, maxRisk: null });
      adjacency.set(key, new Set());
    }
    return nodes.get(key);
  };

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;
    const asset = tx.asset || 'ETH';
    const value = valueOf(tx.value);
    const key = `${source}|${target}|${asset}`;
    if (!edges.has(key)) edges.set(key, { id: key, source, target, asset, totalValue: 0, txCount: 0, transactions: [], maxRisk: null });
    const edge = edges.get(key);
    edge.totalValue += value;
    edge.txCount += 1;
    edge.transactions.push(tx);
    if (tx.risk_score != null) edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);

    const from = ensure(source);
    const to = ensure(target);
    from.txCount += 1; from.outgoing += 1; from.counterparties.add(target); from.outByAsset[asset] = (from.outByAsset[asset] || 0) + value;
    to.txCount += 1; to.incoming += 1; to.counterparties.add(source); to.inByAsset[asset] = (to.inByAsset[asset] || 0) + value;
    if (tx.risk_score != null) {
      const r = Number(tx.risk_score) || 0;
      from.maxRisk = Math.max(from.maxRisk ?? 0, r);
      to.maxRisk = Math.max(to.maxRisk ?? 0, r);
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
      const cur = queue[i];
      for (const next of adjacency.get(cur) || []) {
        if (depth.has(next)) continue;
        depth.set(next, (depth.get(cur) || 0) + 1);
        parent.set(next, cur);
        queue.push(next);
      }
    }
  }

  const positioned = [];
  const rootNode = nodes.get(rootId);
  if (rootNode) positioned.push({ ...rootNode, x: 0, y: 0, depth: 0, isRoot: true, cluster: 0 });

  const directIds = [...(adjacency.get(rootId) || [])];
  const direct = directIds.map(id => nodes.get(id)).filter(Boolean).sort((a, b) => b.txCount - a.txCount);
  direct.forEach((node, index) => {
    const a = index * 2.3999632297;
    const r = 86 + 18 * Math.sqrt(index + 1);
    positioned.push({ ...node, x: Math.cos(a) * r, y: Math.sin(a) * r * 0.74, depth: 1, isRoot: false, cluster: 0 });
  });

  const positionedIds = new Set(positioned.map(n => n.id));
  const byId = new Map(positioned.map(n => [n.id, n]));
  for (const node of nodes.values()) {
    if (positionedIds.has(node.id)) continue;
    const p = byId.get(parent.get(node.id));
    const d = depth.get(node.id) ?? 2;
    const seed = hash01(node.id);
    const a = seed * Math.PI * 2;
    const r = 48 + d * 18 + hash01(`${node.id}:r`) * 32;
    positioned.push({ ...node, x: (p?.x || 0) + Math.cos(a) * r, y: (p?.y || 0) + Math.sin(a) * r * 0.72, depth: d, isRoot: false, cluster: p?.cluster ?? 1 });
    byId.set(node.id, positioned[positioned.length - 1]);
  }

  return { root: rootId, nodes: positioned, edges: [...edges.values()], adjacency };
}

function radiusFor(node) {
  if (node.isRoot) return 10;
  return clamp(6 + Math.log2(node.txCount + node.counterparties.size + 1) * 2.5, 7, 18);
}

function distSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax; const dy = by - ay; const l2 = dx * dx + dy * dy || 1;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function assets(node) {
  const keys = new Set([...Object.keys(node.inByAsset), ...Object.keys(node.outByAsset)]);
  return [...keys].map(asset => ({ asset, incoming: node.inByAsset[asset] || 0, outgoing: node.outByAsset[asset] || 0 }));
}

export default function ReferenceBubbleMap({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });
  const dragRef = useRef(null);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [zoom, setZoom] = useState(1.04);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [showList, setShowList] = useState(false);
  const [query, setQuery] = useState('');
  const [balances, setBalances] = useState({});
  const [balanceLoading, setBalanceLoading] = useState(false);

  const network = useMemo(() => buildNetwork(transactions, root), [transactions, root]);
  const nodeById = useMemo(() => new Map(network.nodes.map(n => [n.id, n])), [network.nodes]);
  const selectedNode = selected?.kind === 'node' ? nodeById.get(selected.id) : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(e => e.id === selected.id) : null;
  const selectedNeighbors = useMemo(() => selectedNode ? new Set(network.adjacency.get(selectedNode.id) || []) : new Set(), [selectedNode, network.adjacency]);
  const selectedBalance = selectedNode ? balances[selectedNode.id] : null;

  useEffect(() => {
    if (!selectedNode || balances[selectedNode.id]) return;
    let cancelled = false;
    setBalanceLoading(true);
    api.getWalletBalance(selectedNode.id)
      .then(data => { if (!cancelled) setBalances(prev => ({ ...prev, [selectedNode.id]: { status: 'ready', ...data } })); })
      .catch(error => { if (!cancelled) setBalances(prev => ({ ...prev, [selectedNode.id]: { status: 'error', message: error.message || 'Balance unavailable' } })); })
      .finally(() => { if (!cancelled) setBalanceLoading(false); });
    return () => { cancelled = true; };
  }, [selectedNode, balances]);

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
        canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#020611'; ctx.fillRect(0, 0, width, height);

      const projected = new Map();
      const centerX = width * 0.58 + pan.x;
      const centerY = height * 0.51 + pan.y;
      network.nodes.forEach(n => projected.set(n.id, { x: centerX + n.x * zoom, y: centerY + n.y * zoom }));

      const edgeHits = [];
      for (const edge of network.edges) {
        const a = projected.get(edge.source); const b = projected.get(edge.target);
        if (!a || !b) continue;
        const active = selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
        const dim = selectedNode && !active;
        const cyan = active || edge.source === network.root || edge.target === network.root;
        ctx.save();
        ctx.strokeStyle = cyan ? '#31bce8' : '#243147';
        ctx.globalAlpha = active ? .72 : dim ? .045 : .34;
        ctx.lineWidth = active ? 1.35 : .8;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
        const ux = dx / len, uy = dy / len; const tx = b.x - ux * 9, ty = b.y - uy * 9;
        ctx.fillStyle = cyan ? '#67d7fa' : '#50617a'; ctx.globalAlpha = active ? .9 : dim ? .05 : .45;
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - ux * 6 - uy * 3, ty - uy * 6 + ux * 3); ctx.lineTo(tx - ux * 6 + uy * 3, ty - uy * 6 - ux * 3); ctx.closePath(); ctx.fill();
        ctx.restore();
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      const nodeHits = [];
      for (const node of network.nodes) {
        const p = projected.get(node.id); if (!p) continue;
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hovered?.kind === 'node' && hovered.id === node.id;
        const connected = selectedNode ? selectedNeighbors.has(node.id) : false;
        const dim = selectedNode && !isSelected && !connected;
        const activeCluster = node.isRoot || node.depth <= 1 || connected || isSelected;
        const r = radiusFor(node) * Math.sqrt(zoom) * (isSelected ? 1.18 : isHovered ? 1.08 : 1);
        const stroke = activeCluster ? '#16c6f4' : '#263550';
        const fill = activeCluster ? '#0d2635' : '#0b1220';
        ctx.save();
        ctx.globalAlpha = dim ? .14 : activeCluster ? .95 : .72;
        const g = ctx.createRadialGradient(p.x - r * .35, p.y - r * .38, r * .08, p.x, p.y, r);
        g.addColorStop(0, activeCluster ? '#4ed8ff' : '#40506a');
        g.addColorStop(.22, activeCluster ? '#163e52' : '#172234');
        g.addColorStop(1, fill);
        ctx.fillStyle = g; ctx.strokeStyle = isSelected ? '#ffffff' : stroke; ctx.lineWidth = isSelected ? 2.4 : 1.6;
        ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.restore();
        nodeHits.push({ id: node.id, x: p.x, y: p.y, r: r + 5 });
      }

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [network, selectedNode, selectedNeighbors, hovered, zoom, pan]);

  function localPoint(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function hitAt(event) {
    const p = localPoint(event);
    const n = [...hitRef.current.nodes].reverse().find(h => Math.hypot(p.x - h.x, p.y - h.y) <= h.r);
    if (n) return { kind: 'node', id: n.id };
    const e = [...hitRef.current.edges].reverse().find(h => distSeg(p.x, p.y, h.ax, h.ay, h.bx, h.by) <= 5);
    return e ? { kind: 'edge', id: e.id } : null;
  }

  function onPointerDown(event) {
    const hit = hitAt(event);
    if (hit) { setSelected(hit); return; }
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

  function reset() { setPan({ x: 0, y: 0 }); setZoom(1.04); setSelected(null); }
  function retryBalance() {
    if (!selectedNode) return;
    setBalances(prev => { const next = { ...prev }; delete next[selectedNode.id]; return next; });
  }

  const list = network.nodes.filter(n => !query || n.id.includes(query.toLowerCase())).sort((a, b) => b.txCount - a.txCount);
  const totalIn = selectedNode ? Object.values(selectedNode.inByAsset).reduce((a, b) => a + b, 0) : 0;
  const totalOut = selectedNode ? Object.values(selectedNode.outByAsset).reduce((a, b) => a + b, 0) : 0;

  return <section className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#020611] shadow-2xl shadow-black/40">
    <div className="relative min-h-[760px] bg-[#020611]">
      <div className="absolute left-0 right-0 top-0 z-20 flex items-center justify-between border-b border-white/[0.06] bg-[#202126]/95 px-4 py-2.5 backdrop-blur">
        <div className="text-sm font-semibold text-slate-100">ChainScope Maps</div>
        <div className="rounded-full bg-white/[0.07] px-5 py-2 text-sm font-semibold text-slate-100">Bubble Map</div>
        <div className="flex items-center gap-2"><button onClick={() => canvasRef.current?.closest('section')?.requestFullscreen?.()} className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">⛶</button></div>
      </div>

      <div className="absolute left-4 top-16 z-30 flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#171923]/95 p-3 shadow-2xl backdrop-blur">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-cyan-400/15 text-cyan-300">◉</div>
        <div><p className="text-sm font-semibold text-white">Ethereum wallet</p><p className="font-mono text-[11px] text-slate-400">{short(root)}</p></div>
        <div className="ml-2 h-7 w-px bg-white/10" />
        <button onClick={reset} className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/[0.05]">Reset</button>
      </div>

      <button onClick={() => setShowList(true)} className="absolute right-4 top-16 z-30 rounded-xl border border-white/[0.08] bg-[#171923]/95 px-4 py-3 text-sm font-medium text-slate-200 shadow-xl backdrop-blur">Address List ▦</button>

      <canvas ref={canvasRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }} onPointerLeave={() => setHovered(null)} onWheel={e => { e.preventDefault(); setZoom(z => clamp(z * (e.deltaY < 0 ? 1.11 : .9), .45, 2.8)); }} className="h-[760px] w-full touch-none cursor-grab active:cursor-grabbing" />

      {selectedNode && <aside className="absolute left-0 top-[112px] z-40 w-[360px] max-w-[88vw] rounded-r-2xl border-y border-r border-white/[0.09] bg-[#181a24]/97 p-4 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-4">
          <div><p className="text-[10px] uppercase tracking-[.18em] text-slate-500">Selected wallet</p><p className="mt-1 font-mono text-sm text-white">{short(selectedNode.id)}</p></div>
          <button onClick={() => setSelected(null)} className="text-2xl leading-none text-slate-500 hover:text-white">×</button>
        </div>

        <div className="mt-4 rounded-lg border-l-4 border-cyan-400 bg-white/[0.04] px-3 py-3"><div className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-200">Live ETH balance</span><span className="h-2.5 w-2.5 rounded-full bg-cyan-400" /></div>
          <div className="mt-2 text-2xl font-semibold text-white">{balanceLoading ? 'Loading…' : selectedBalance?.status === 'ready' ? `${Number(selectedBalance.balance_eth).toLocaleString(undefined, { maximumFractionDigits: 8 })} ETH` : 'Unavailable'}</div>
          {selectedBalance?.status === 'ready' && <p className="mt-1 text-[11px] text-slate-500">mainnet · block {selectedBalance.block_number}</p>}
          {selectedBalance?.status === 'error' && <button onClick={retryBalance} className="mt-2 text-xs text-cyan-300">Retry live balance</button>}
        </div>

        <div className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between"><span className="text-slate-400">↙ IN</span><span className="text-slate-100">{totalIn.toLocaleString(undefined, { maximumFractionDigits: 6 })} observed</span></div>
          <div className="flex items-center justify-between"><span className="text-slate-400">↗ OUT</span><span className="text-slate-100">{totalOut.toLocaleString(undefined, { maximumFractionDigits: 6 })} observed</span></div>
          <div className="flex items-center justify-between"><span className="text-slate-400">Transfers</span><span className="text-slate-100">{selectedNode.txCount}</span></div>
          <div className="flex items-center justify-between"><span className="text-slate-400">Counterparties</span><span className="text-slate-100">{selectedNode.counterparties.size}</span></div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">{assets(selectedNode).slice(0, 4).map(row => <span key={row.asset} className="rounded-full bg-white/[0.06] px-3 py-1 text-xs text-slate-300">{row.asset}</span>)}</div>
        <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-5 inline-flex text-xs text-cyan-300 hover:underline">View address evidence ↗</a>
      </aside>}

      {selectedEdge && <aside className="absolute left-0 top-[112px] z-40 w-[360px] max-w-[88vw] rounded-r-2xl border-y border-r border-white/[0.09] bg-[#181a24]/97 p-4 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-4"><div><p className="text-[10px] uppercase tracking-[.18em] text-slate-500">Transfer relationship</p><p className="mt-1 font-mono text-xs text-white">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div><button onClick={() => setSelected(null)} className="text-2xl text-slate-500">×</button></div>
        <p className="mt-4 text-xl font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p><p className="mt-1 text-xs text-slate-500">{selectedEdge.txCount} observed transaction{selectedEdge.txCount === 1 ? '' : 's'}</p>
        <div className="mt-4 max-h-48 space-y-2 overflow-auto">{selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.value}`} onClick={() => onSelect?.(tx)} className="w-full rounded-lg bg-white/[0.035] p-2 text-left"><span className="font-mono text-xs text-cyan-300">{short(tx.hash)}</span></button>)}</div>
      </aside>}

      {showList && <aside className="absolute right-4 top-28 z-50 w-[360px] max-w-[88vw] rounded-xl border border-white/[0.09] bg-[#181a24]/98 p-4 shadow-2xl backdrop-blur-xl"><div className="flex items-center justify-between"><div><p className="text-sm font-semibold text-white">Address List</p><p className="text-xs text-slate-500">Loaded evidence</p></div><button onClick={() => setShowList(false)} className="text-2xl text-slate-500">×</button></div><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter address" className="mt-3 h-9 w-full rounded-lg border border-white/[0.08] bg-[#0e1118] px-3 font-mono text-xs text-slate-200 outline-none" /><div className="mt-3 max-h-[520px] space-y-1 overflow-auto">{list.map(node => <button key={node.id} onClick={() => { setSelected({ kind: 'node', id: node.id }); setShowList(false); }} className="w-full rounded-lg px-3 py-2 text-left hover:bg-white/[0.05]"><div className="flex items-center justify-between"><span className="font-mono text-xs text-slate-200">{short(node.id)}</span><span className="text-[10px] text-slate-500">{node.txCount} tx</span></div></button>)}</div></aside>}

      <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg bg-black/25 px-3 py-2 text-[11px] text-slate-500">Drag · wheel zoom · click wallet</div>
    </div>
    <div className="border-t border-white/[0.06] bg-[#090d16] px-4 py-3 text-[11px] text-slate-500">Loaded ChainScope evidence only. Bubble proximity visualizes observed transfer relationships and does not prove common ownership.</div>
  </section>;
}
