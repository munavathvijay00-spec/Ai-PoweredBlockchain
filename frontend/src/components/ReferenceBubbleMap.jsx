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
    from.txCount += 1;
    from.outgoing += 1;
    from.counterparties.add(target);
    from.outByAsset[asset] = (from.outByAsset[asset] || 0) + value;
    to.txCount += 1;
    to.incoming += 1;
    to.counterparties.add(source);
    to.inByAsset[asset] = (to.inByAsset[asset] || 0) + value;
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
  if (rootNode) positioned.push({ ...rootNode, x: 0, y: 0, z: 0, depth: 0, isRoot: true, cluster: 0 });

  const directIds = [...(adjacency.get(rootId) || [])];
  const direct = directIds.map(id => nodes.get(id)).filter(Boolean).sort((a, b) => b.txCount - a.txCount);
  direct.forEach((node, index) => {
    const a = index * 2.3999632297;
    const r = 86 + 18 * Math.sqrt(index + 1);
    const z = (hash01(`${node.id}:z`) - 0.5) * 150;
    positioned.push({ ...node, x: Math.cos(a) * r, y: Math.sin(a) * r * 0.74, z, depth: 1, isRoot: false, cluster: 0 });
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
    positioned.push({
      ...node,
      x: (p?.x || 0) + Math.cos(a) * r,
      y: (p?.y || 0) + Math.sin(a) * r * 0.72,
      z: (p?.z || 0) + (hash01(`${node.id}:z`) - 0.5) * 90,
      depth: d,
      isRoot: false,
      cluster: p?.cluster ?? 1,
    });
    byId.set(node.id, positioned[positioned.length - 1]);
  }

  return { root: rootId, nodes: positioned, edges: [...edges.values()], adjacency };
}

function radiusFor(node) {
  if (node.isRoot) return 11;
  return clamp(6 + Math.log2((node.txCount || 0) + (node.counterparties?.size || 0) + 1) * 2.5, 7, 18);
}

function distSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const l2 = dx * dx + dy * dy || 1;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function assets(node) {
  const keys = new Set([...Object.keys(node.inByAsset), ...Object.keys(node.outByAsset)]);
  return [...keys].map(asset => ({ asset, incoming: node.inByAsset[asset] || 0, outgoing: node.outByAsset[asset] || 0 }));
}

function nodeTheme(node, activeCluster) {
  const risk = Number(node.maxRisk || 0);
  if (risk >= 70) return { rim: '#fb7185', glow: 'rgba(251,113,133,.9)', hot: '#ffe4e6', mid: '#9f2942', deep: '#2c0a13' };
  if (!node.isRoot && node.txCount >= 8) return { rim: '#a78bfa', glow: 'rgba(167,139,250,.82)', hot: '#ede9fe', mid: '#6d4bd1', deep: '#1c1237' };
  if (activeCluster) return { rim: '#20d0ff', glow: 'rgba(29,184,232,.58)', hot: '#d7f8ff', mid: '#1688ad', deep: '#020c16' };
  return { rim: '#2d415b', glow: 'transparent', hot: '#7890aa', mid: '#26364a', deep: '#08111e' };
}

export default function ReferenceBubbleMap({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });
  const dragRef = useRef(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const cameraRef = useRef({ x: 0, y: 0, zoom: 1 });
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
  const graphLoad = network.nodes.length + network.edges.length;
  const quality = graphLoad > 900 ? 'low' : graphLoad > 420 ? 'medium' : 'high';

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

    const draw = now => {
      const t = now * 0.001;
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, quality === 'high' ? 2 : 1.5);
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const targetCamX = selectedNode ? -selectedNode.x * zoom * 0.36 : 0;
      const targetCamY = selectedNode ? -selectedNode.y * zoom * 0.28 : 0;
      const targetCamZoom = selectedNode ? 1.08 : 1;
      cameraRef.current.x += (targetCamX - cameraRef.current.x) * 0.075;
      cameraRef.current.y += (targetCamY - cameraRef.current.y) * 0.075;
      cameraRef.current.zoom += (targetCamZoom - cameraRef.current.zoom) * 0.06;

      const bg = ctx.createRadialGradient(width * 0.58, height * 0.5, 0, width * 0.58, height * 0.5, Math.max(width, height) * 0.75);
      bg.addColorStop(0, '#061426');
      bg.addColorStop(0.52, '#020914');
      bg.addColorStop(1, '#01040b');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, width, height);

      const centerX = width * 0.58 + pan.x + cameraRef.current.x;
      const centerY = height * 0.51 + pan.y + cameraRef.current.y;
      const effectiveZoom = zoom * cameraRef.current.zoom;
      const parallaxX = pointerRef.current.x * 8;
      const parallaxY = pointerRef.current.y * 5;

      ctx.save();
      ctx.translate(centerX + parallaxX * 0.2, centerY + parallaxY * 0.2);
      ctx.strokeStyle = 'rgba(20, 174, 229, 0.095)';
      ctx.lineWidth = 1;
      const orbitCount = quality === 'low' ? 2 : 4;
      for (let i = 0; i < orbitCount; i += 1) {
        const wobble = Math.sin(t * 0.22 + i) * 4;
        ctx.beginPath();
        ctx.ellipse(0, 0, 155 + i * 68 + wobble, (155 + i * 68) * 0.57, t * 0.018 + i * 0.47, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();

      const starCount = quality === 'low' ? 18 : quality === 'medium' ? 32 : 56;
      for (let i = 0; i < starCount; i += 1) {
        const sx = (hash01(`star-x-${i}`) * width + t * (2 + hash01(`star-v-${i}`) * 5)) % width;
        const sy = hash01(`star-y-${i}`) * height;
        const twinkle = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(t * (0.7 + hash01(`star-s-${i}`)) + i));
        ctx.fillStyle = `rgba(71, 213, 255, ${twinkle * 0.45})`;
        ctx.beginPath();
        ctx.arc(sx, sy, 0.55 + hash01(`star-r-${i}`) * 1.35, 0, Math.PI * 2);
        ctx.fill();
      }

      const yaw = Math.sin(t * 0.16) * 0.105 + pointerRef.current.x * 0.055;
      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);
      const projected = new Map();
      network.nodes.forEach(n => {
        const float = n.isRoot ? 0 : Math.sin(t * (0.45 + hash01(`${n.id}:speed`) * 0.5) + hash01(`${n.id}:phase`) * Math.PI * 2) * (quality === 'low' ? 1.4 : 2.1 + hash01(`${n.id}:amp`) * 2.4);
        const rx = n.x * cosY - (n.z || 0) * sinY;
        const rz = n.x * sinY + (n.z || 0) * cosY;
        const perspective = clamp(1.08 - rz / 880, 0.78, 1.28);
        projected.set(n.id, {
          x: centerX + rx * effectiveZoom * perspective + parallaxX * (0.12 + (1 - perspective) * 0.6),
          y: centerY + (n.y + float) * effectiveZoom * perspective + parallaxY * (0.12 + (1 - perspective) * 0.6),
          z: rz,
          scale: perspective,
        });
      });

      const edgeHits = [];
      const particleCap = quality === 'low' ? 1 : quality === 'medium' ? 2 : 3;
      for (const edge of network.edges) {
        const a = projected.get(edge.source);
        const b = projected.get(edge.target);
        if (!a || !b) continue;
        const active = selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
        const hoveredEdge = hovered?.kind === 'edge' && hovered.id === edge.id;
        const dim = selectedNode && !active;
        const rootEdge = edge.source === network.root || edge.target === network.root;
        const cyan = active || rootEdge || hoveredEdge;
        const depthAlpha = clamp((a.scale + b.scale) * 0.5, 0.72, 1.2);

        ctx.save();
        ctx.strokeStyle = active ? '#67e8f9' : cyan ? '#25c9fb' : '#29435c';
        ctx.globalAlpha = (active ? 0.96 : hoveredEdge ? 0.78 : dim ? 0.025 : rootEdge ? 0.5 : 0.28) * depthAlpha;
        ctx.lineWidth = active ? 2.05 : hoveredEdge ? 1.6 : rootEdge ? 1.05 : 0.72;
        ctx.shadowColor = cyan ? 'rgba(37,201,251,.82)' : 'transparent';
        ctx.shadowBlur = active ? 14 : hoveredEdge ? 9 : rootEdge ? 5 : 0;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();

        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len;
        const uy = dy / len;
        const targetRadius = (radiusFor(nodeById.get(edge.target) || {}) || 8) * (b.scale || 1) * Math.sqrt(effectiveZoom);
        const tx = b.x - ux * (targetRadius + 4);
        const ty = b.y - uy * (targetRadius + 4);
        ctx.save();
        ctx.fillStyle = cyan ? '#70e4ff' : '#506783';
        ctx.globalAlpha = active ? 1 : dim ? 0.04 : 0.48;
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(tx - ux * 6 - uy * 3, ty - uy * 6 + ux * 3);
        ctx.lineTo(tx - ux * 6 + uy * 3, ty - uy * 6 - ux * 3);
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        if (!dim) {
          const particleCount = Math.min(particleCap, Math.max(1, Math.ceil(Math.log2(edge.txCount + 1))));
          for (let i = 0; i < particleCount; i += 1) {
            const speed = (active ? 0.15 : 0.085) + hash01(`${edge.id}:speed:${i}`) * 0.07;
            const phase = hash01(`${edge.id}:phase:${i}`);
            const p = (phase + t * speed) % 1;
            const px = a.x + dx * p;
            const py = a.y + dy * p;
            const pr = active ? 2.8 : rootEdge ? 2 : 1.45;
            ctx.save();
            ctx.globalAlpha = active ? 1 : rootEdge ? 0.82 : 0.48;
            ctx.fillStyle = active ? '#d8fbff' : '#7be7ff';
            ctx.shadowColor = '#17c9ff';
            ctx.shadowBlur = active ? 15 : 7;
            ctx.beginPath();
            ctx.arc(px, py, pr, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }

        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      const orderedNodes = [...network.nodes].sort((left, right) => (projected.get(left.id)?.z || 0) - (projected.get(right.id)?.z || 0));
      const nodeHits = [];
      for (const node of orderedNodes) {
        const p = projected.get(node.id);
        if (!p) continue;
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hovered?.kind === 'node' && hovered.id === node.id;
        const connected = selectedNode ? selectedNeighbors.has(node.id) : false;
        const dim = selectedNode && !isSelected && !connected;
        const activeCluster = node.isRoot || node.depth <= 1 || connected || isSelected;
        const theme = nodeTheme(node, activeCluster);
        const breathe = node.isRoot ? 1 + Math.sin(t * 2.15) * 0.05 : 1 + Math.sin(t * 0.8 + hash01(node.id) * 8) * (quality === 'low' ? 0.009 : 0.018);
        const r = radiusFor(node) * Math.sqrt(effectiveZoom) * p.scale * breathe * (isSelected ? 1.28 : isHovered ? 1.14 : 1);

        if (node.isRoot) {
          for (let ring = 0; ring < (quality === 'low' ? 2 : 3); ring += 1) {
            const phase = (t * 0.32 + ring / 3) % 1;
            ctx.save();
            ctx.strokeStyle = `rgba(41, 211, 255, ${0.3 * (1 - phase)})`;
            ctx.lineWidth = 1.2;
            ctx.shadowColor = '#1bd4ff';
            ctx.shadowBlur = quality === 'low' ? 5 : 10;
            ctx.beginPath();
            ctx.arc(p.x, p.y, r + 8 + phase * 30, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        }

        ctx.save();
        ctx.globalAlpha = dim ? 0.075 : activeCluster ? 0.98 : 0.68;
        if (activeCluster) {
          ctx.shadowColor = node.isRoot ? 'rgba(26, 212, 255, .95)' : theme.glow;
          ctx.shadowBlur = node.isRoot ? 28 : isHovered || isSelected ? 22 : 9;
        }

        const g = ctx.createRadialGradient(p.x - r * 0.38, p.y - r * 0.42, r * 0.04, p.x, p.y, r * 1.12);
        g.addColorStop(0, theme.hot);
        g.addColorStop(0.1, activeCluster ? theme.rim : theme.hot);
        g.addColorStop(0.28, theme.mid);
        g.addColorStop(0.68, theme.deep);
        g.addColorStop(1, '#020711');
        ctx.fillStyle = g;
        ctx.strokeStyle = isSelected ? '#ffffff' : theme.rim;
        ctx.lineWidth = isSelected ? 2.8 : isHovered ? 2.25 : 1.55;
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        if (!dim && quality !== 'low') {
          const sheen = ctx.createLinearGradient(p.x - r, p.y - r, p.x + r, p.y + r);
          sheen.addColorStop(0, 'rgba(255,255,255,.42)');
          sheen.addColorStop(0.22, 'rgba(255,255,255,.08)');
          sheen.addColorStop(0.52, 'rgba(255,255,255,0)');
          ctx.fillStyle = sheen;
          ctx.beginPath();
          ctx.arc(p.x, p.y, r * 0.94, Math.PI * 1.08, Math.PI * 1.72);
          ctx.lineTo(p.x, p.y);
          ctx.closePath();
          ctx.fill();

          ctx.fillStyle = 'rgba(255,255,255,.78)';
          ctx.globalAlpha *= 0.72;
          ctx.beginPath();
          ctx.arc(p.x - r * 0.34, p.y - r * 0.38, Math.max(1, r * 0.11), 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
        nodeHits.push({ id: node.id, x: p.x, y: p.y, r: r + 6 });
      }

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [network, nodeById, selectedNode, selectedNeighbors, hovered, zoom, pan, quality]);

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
    if (hit) {
      setSelected(hit);
      return;
    }
    dragRef.current = { x: event.clientX, y: event.clientY, pan };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) {
      pointerRef.current = {
        x: clamp(((event.clientX - rect.left) / rect.width - 0.5) * 2, -1, 1),
        y: clamp(((event.clientY - rect.top) / rect.height - 0.5) * 2, -1, 1),
      };
    }
    if (dragRef.current) {
      setPan({ x: dragRef.current.pan.x + event.clientX - dragRef.current.x, y: dragRef.current.pan.y + event.clientY - dragRef.current.y });
      return;
    }
    setHovered(hitAt(event));
  }

  function reset() {
    setPan({ x: 0, y: 0 });
    setZoom(1.04);
    setSelected(null);
    cameraRef.current = { x: 0, y: 0, zoom: 1 };
    pointerRef.current = { x: 0, y: 0 };
  }

  function retryBalance() {
    if (!selectedNode) return;
    setBalances(prev => {
      const next = { ...prev };
      delete next[selectedNode.id];
      return next;
    });
  }

  const list = network.nodes.filter(n => !query || n.id.includes(query.toLowerCase())).sort((a, b) => b.txCount - a.txCount);
  const totalIn = selectedNode ? Object.values(selectedNode.inByAsset).reduce((a, b) => a + b, 0) : 0;
  const totalOut = selectedNode ? Object.values(selectedNode.outByAsset).reduce((a, b) => a + b, 0) : 0;

  return <section className="relative overflow-hidden rounded-2xl border border-cyan-300/[0.09] bg-[#020611] shadow-2xl shadow-black/50">
    <div className="relative min-h-[760px] bg-[#020611]">
      <div className="absolute left-0 right-0 top-0 z-20 flex items-center justify-between border-b border-white/[0.06] bg-[#202126]/95 px-4 py-2.5 backdrop-blur">
        <div className="text-sm font-semibold text-slate-100">ChainScope Maps</div>
        <div className="rounded-full border border-cyan-300/10 bg-white/[0.07] px-5 py-2 text-sm font-semibold text-slate-100 shadow-lg shadow-cyan-950/20">Bubble Map</div>
        <div className="flex items-center gap-2"><span className="hidden text-[10px] uppercase tracking-[.16em] text-slate-600 sm:inline">{quality} render</span><button onClick={() => canvasRef.current?.closest('section')?.requestFullscreen?.()} className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300 hover:border-cyan-300/20 hover:text-cyan-200">⛶</button></div>
      </div>

      <div className="absolute left-4 top-16 z-30 flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#171923]/90 p-3 shadow-2xl backdrop-blur-xl">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-cyan-400/15 text-cyan-300 shadow-lg shadow-cyan-500/10">◉</div>
        <div><p className="text-sm font-semibold text-white">Ethereum wallet</p><p className="font-mono text-[11px] text-slate-400">{short(root)}</p></div>
        <div className="ml-2 h-7 w-px bg-white/10" />
        <button onClick={reset} className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/[0.05] hover:text-cyan-200">Reset</button>
      </div>

      <button onClick={() => setShowList(true)} className="absolute right-4 top-16 z-30 rounded-xl border border-white/[0.08] bg-[#171923]/90 px-4 py-3 text-sm font-medium text-slate-200 shadow-xl backdrop-blur-xl hover:border-cyan-300/20 hover:text-cyan-200">Address List ▦</button>

      <div className="pointer-events-none absolute right-4 top-[116px] z-20 flex flex-wrap justify-end gap-2 text-[10px]">
        <span className="rounded-full border border-cyan-300/10 bg-cyan-300/[0.05] px-2 py-1 text-cyan-200">root / standard</span>
        <span className="rounded-full border border-violet-300/10 bg-violet-300/[0.05] px-2 py-1 text-violet-200">high activity</span>
        <span className="rounded-full border border-rose-300/10 bg-rose-300/[0.05] px-2 py-1 text-rose-200">high risk signal</span>
      </div>

      <canvas
        ref={canvasRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => { dragRef.current = null; }}
        onPointerCancel={() => { dragRef.current = null; }}
        onPointerLeave={() => { setHovered(null); pointerRef.current = { x: 0, y: 0 }; }}
        onWheel={e => { e.preventDefault(); setZoom(z => clamp(z * (e.deltaY < 0 ? 1.11 : 0.9), 0.45, 2.8)); }}
        className="h-[760px] w-full touch-none cursor-grab active:cursor-grabbing"
      />

      {selectedNode && <aside className="absolute left-0 top-[112px] z-40 w-[360px] max-w-[88vw] rounded-r-2xl border-y border-r border-white/[0.09] bg-[#181a24]/97 p-4 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-4">
          <div><p className="text-[10px] uppercase tracking-[.18em] text-slate-500">Selected wallet</p><p className="mt-1 font-mono text-sm text-white">{short(selectedNode.id)}</p><p className="mt-1 text-[10px] text-cyan-300/70">Camera focused · connected paths emphasized</p></div>
          <button onClick={() => setSelected(null)} className="text-2xl leading-none text-slate-500 hover:text-white">×</button>
        </div>

        <div className="mt-4 rounded-lg border-l-4 border-cyan-400 bg-white/[0.04] px-3 py-3"><div className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-200">Live ETH balance</span><span className="h-2.5 w-2.5 rounded-full bg-cyan-400 shadow-lg shadow-cyan-300/60" /></div>
          <div className="mt-2 text-2xl font-semibold text-white">{balanceLoading ? 'Loading…' : selectedBalance?.status === 'ready' ? `${Number(selectedBalance.balance_eth).toLocaleString(undefined, { maximumFractionDigits: 8 })} ETH` : 'Unavailable'}</div>
          {selectedBalance?.status === 'ready' && <p className="mt-1 text-[11px] text-slate-500">mainnet · block {selectedBalance.block_number}</p>}
          {selectedBalance?.status === 'error' && <button onClick={retryBalance} className="mt-2 text-xs text-cyan-300">Retry live balance</button>}
        </div>

        <div className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between"><span className="text-slate-400">↙ Observed IN</span><span className="text-slate-100">{totalIn.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></div>
          <div className="flex items-center justify-between"><span className="text-slate-400">↗ Observed OUT</span><span className="text-slate-100">{totalOut.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></div>
          <p className="-mt-1 text-[10px] leading-4 text-slate-600">Observed totals use only transaction evidence currently loaded into this graph; they are not lifetime wallet totals.</p>
          <div className="flex items-center justify-between"><span className="text-slate-400">Transfers</span><span className="text-slate-100">{selectedNode.txCount}</span></div>
          <div className="flex items-center justify-between"><span className="text-slate-400">Counterparties</span><span className="text-slate-100">{selectedNode.counterparties.size}</span></div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">{assets(selectedNode).slice(0, 4).map(row => <span key={row.asset} className="rounded-full bg-white/[0.06] px-3 py-1 text-xs text-slate-300">{row.asset}</span>)}</div>
        <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-5 inline-flex text-xs text-cyan-300 hover:underline">View address evidence ↗</a>
      </aside>}

      {selectedEdge && <aside className="absolute left-0 top-[112px] z-40 w-[360px] max-w-[88vw] rounded-r-2xl border-y border-r border-white/[0.09] bg-[#181a24]/97 p-4 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-4"><div><p className="text-[10px] uppercase tracking-[.18em] text-slate-500">Transfer relationship</p><p className="mt-1 font-mono text-xs text-white">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div><button onClick={() => setSelected(null)} className="text-2xl text-slate-500">×</button></div>
        <p className="mt-4 text-xl font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p><p className="mt-1 text-xs text-slate-500">{selectedEdge.txCount} observed transaction{selectedEdge.txCount === 1 ? '' : 's'}</p>
        <div className="mt-4 max-h-48 space-y-2 overflow-auto">{selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.value}`} onClick={() => onSelect?.(tx)} className="w-full rounded-lg bg-white/[0.035] p-2 text-left hover:bg-cyan-300/[0.06]"><span className="font-mono text-xs text-cyan-300">{short(tx.hash)}</span></button>)}</div>
      </aside>}

      {showList && <aside className="absolute right-4 top-28 z-50 w-[360px] max-w-[88vw] rounded-xl border border-white/[0.09] bg-[#181a24]/98 p-4 shadow-2xl backdrop-blur-xl"><div className="flex items-center justify-between"><div><p className="text-sm font-semibold text-white">Address List</p><p className="text-xs text-slate-500">Loaded evidence</p></div><button onClick={() => setShowList(false)} className="text-2xl text-slate-500">×</button></div><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter address" className="mt-3 h-9 w-full rounded-lg border border-white/[0.08] bg-[#0e1118] px-3 font-mono text-xs text-slate-200 outline-none" /><div className="mt-3 max-h-[520px] space-y-1 overflow-auto">{list.map(node => <button key={node.id} onClick={() => { setSelected({ kind: 'node', id: node.id }); setShowList(false); }} className="w-full rounded-lg px-3 py-2 text-left hover:bg-white/[0.05]"><div className="flex items-center justify-between"><span className="font-mono text-xs text-slate-200">{short(node.id)}</span><span className="text-[10px] text-slate-500">{node.txCount} tx</span></div></button>)}</div></aside>}

      <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-white/[0.05] bg-black/30 px-3 py-2 text-[11px] text-slate-500 backdrop-blur">Drag · wheel zoom · hover path · click wallet to focus</div>
    </div>
    <div className="border-t border-white/[0.06] bg-[#090d16] px-4 py-3 text-[11px] text-slate-500">Loaded ChainScope evidence only. Animated particles visualize observed transfer direction; visual depth, color and proximity do not prove ownership, intent or causal attribution.</div>
  </section>;
}