import { useEffect, useMemo, useRef, useState } from 'react';
import BubbleInvestigationGraph from './BubbleInvestigationGraph';

const normalized = value => String(value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const COLORS = ['#38bdf8','#8b5cf6','#22c55e','#f59e0b','#ef4444','#14b8a6','#60a5fa','#d946ef','#eab308','#10b981'];

function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function buildDenseGraph(transactions, rootAddress, nodeContext) {
  const root = normalized(rootAddress);
  const edges = transactions
    .filter(tx => tx.from_address && tx.to_address && tx.hash)
    .map((tx, index) => ({
      id: `${tx.hash}-${index}`,
      from: normalized(tx.from_address),
      to: normalized(tx.to_address),
      risk: Number(tx.risk_score || 0),
      tx,
    }));

  const ids = [...new Set(edges.flatMap(edge => [edge.from, edge.to]))];
  if (root && !ids.includes(root)) ids.unshift(root);

  const metrics = new Map(ids.map(id => [id, { incoming: 0, outgoing: 0, transfers: 0, peers: new Set(), maxRisk: Number(nodeContext[id]?.maxRisk || 0) }]));
  edges.forEach(edge => {
    const from = metrics.get(edge.from), to = metrics.get(edge.to);
    if (from) { from.outgoing += 1; from.transfers += 1; from.peers.add(edge.to); from.maxRisk = Math.max(from.maxRisk, edge.risk); }
    if (to) { to.incoming += 1; to.transfers += 1; to.peers.add(edge.from); to.maxRisk = Math.max(to.maxRisk, edge.risk); }
  });

  const nonRoot = ids.filter(id => id !== root);
  const ranked = [...nonRoot].sort((a, b) => {
    const am = metrics.get(a), bm = metrics.get(b);
    return ((bm?.transfers || 0) * 4 + (bm?.peers?.size || 0) * 2) - ((am?.transfers || 0) * 4 + (am?.peers?.size || 0) * 2);
  });

  const ringCapacity = 24;
  const nodes = [{ id: root, x: 0, y: 0, z: 0, ring: 0 }];
  ranked.forEach((id, index) => {
    const ring = Math.floor(index / ringCapacity) + 1;
    const inRing = index % ringCapacity;
    const countThisRing = Math.min(ringCapacity, ranked.length - (ring - 1) * ringCapacity);
    const seed = hash(id);
    const jitter = ((seed % 1000) / 1000 - 0.5) * 0.16;
    const angle = (Math.PI * 2 * inRing / Math.max(1, countThisRing)) + ring * 0.37 + jitter;
    const radius = 145 + ring * 118;
    const z = (((seed >>> 8) % 1000) / 1000 - 0.5) * Math.min(140, 42 + ring * 18);
    nodes.push({ id, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius * 0.72, z, ring });
  });

  const nodeMap = new Map(nodes.map(node => [node.id, node]));
  return { root, nodes, nodeMap, edges, metrics, sceneRadius: 160 + Math.max(1, Math.ceil(ranked.length / ringCapacity)) * 118 };
}

function rotate(node, camera) {
  const px = node.x - camera.focus[0], py = node.y - camera.focus[1], pz = node.z - camera.focus[2];
  const cy = Math.cos(camera.yaw), sy = Math.sin(camera.yaw), cp = Math.cos(camera.pitch), sp = Math.sin(camera.pitch);
  const x1 = px * cy + pz * sy, z1 = -px * sy + pz * cy;
  return { x: x1, y: py * cp - z1 * sp, z: py * sp + z1 * cp };
}

function project(node, camera, width, height) {
  const p = rotate(node, camera);
  const depth = Math.max(430, 1180 - p.z);
  const perspective = 1180 / depth;
  return { x: width / 2 + p.x * perspective * camera.zoom, y: height / 2 + p.y * perspective * camera.zoom, z: p.z, perspective };
}

function DenseBubbleGraph({ transactions, rootAddress, onExpandAddress, expandingAddress, expandedAddresses, nodeContext }) {
  const canvasRef = useRef(null);
  const hitRef = useRef([]);
  const dragRef = useRef(null);
  const animationRef = useRef(null);
  const graph = useMemo(() => buildDenseGraph(transactions, rootAddress, nodeContext), [transactions, rootAddress, nodeContext]);
  const expanded = useMemo(() => new Set(expandedAddresses.map(normalized)), [expandedAddresses]);
  const cameraRef = useRef({ yaw: 0.08, pitch: -0.05, zoom: 0.7, targetZoom: 0.7, focus: [0,0,0], targetFocus: [0,0,0] });
  const [selected, setSelected] = useState('');
  const [hovered, setHovered] = useState('');
  const [query, setQuery] = useState('');

  const fitCamera = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = canvas.clientWidth || 900;
    const height = canvas.clientHeight || 700;
    const usable = Math.min(width * 0.44, height * 0.42);
    const zoom = clamp(usable / Math.max(260, graph.sceneRadius), 0.24, 1.45);
    cameraRef.current.targetZoom = zoom;
    cameraRef.current.targetFocus = [0,0,0];
  };

  useEffect(() => { fitCamera(); }, [graph]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return undefined;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let stopped = false;

    const draw = () => {
      if (stopped) return;
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const camera = cameraRef.current;
      camera.zoom += (camera.targetZoom - camera.zoom) * 0.12;
      for (let i = 0; i < 3; i += 1) camera.focus[i] += (camera.targetFocus[i] - camera.focus[i]) * 0.12;

      const bg = ctx.createRadialGradient(width * 0.5, height * 0.46, 20, width * 0.5, height * 0.46, Math.max(width, height) * 0.75);
      bg.addColorStop(0, '#10233b'); bg.addColorStop(0.46, '#07111f'); bg.addColorStop(1, '#02060b');
      ctx.fillStyle = bg; ctx.fillRect(0, 0, width, height);

      const projected = new Map(graph.nodes.map(node => [node.id, project(node, camera, width, height)]));
      graph.edges.forEach(edge => {
        const a = projected.get(edge.from), b = projected.get(edge.to);
        if (!a || !b) return;
        const related = selected && (edge.from === selected || edge.to === selected);
        ctx.save();
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = edge.tx.category === 'erc20' ? 'rgba(196,181,253,.18)' : 'rgba(125,211,252,.16)';
        ctx.globalAlpha = selected && !related ? 0.15 : related ? 0.82 : 0.5;
        ctx.lineWidth = related ? 1.5 : 0.7; ctx.stroke(); ctx.restore();
      });

      const hits = [];
      [...graph.nodes].sort((a,b) => (projected.get(a.id)?.z || 0) - (projected.get(b.id)?.z || 0)).forEach(node => {
        const p = projected.get(node.id); if (!p) return;
        const metric = graph.metrics.get(node.id);
        const isRoot = node.id === graph.root, isSelected = node.id === selected, isHovered = node.id === hovered;
        const activity = Math.log2(2 + (metric?.transfers || 0) + (metric?.peers?.size || 0));
        const radius = clamp((isRoot ? 18 : 5.5 + activity * 2.2) * clamp(p.perspective, 0.82, 1.28) * (isSelected ? 1.25 : isHovered ? 1.12 : 1), 4.5, isRoot ? 28 : 18);
        let color = COLORS[node.ring % COLORS.length];
        if (isRoot) color = '#31d7f5'; else if (isSelected) color = '#ffd166'; else if ((nodeContext[node.id]?.entityLabels || []).length) color = '#34d399'; else if (Number(metric?.maxRisk || 0) >= 70) color = '#fb7185'; else if (expanded.has(node.id)) color = '#f59e0b';
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius * 2.1);
        glow.addColorStop(0, `${color}55`); glow.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(p.x, p.y, radius * 2.1, 0, Math.PI * 2); ctx.fill();
        const sphere = ctx.createRadialGradient(p.x - radius * 0.32, p.y - radius * 0.34, radius * 0.05, p.x, p.y, radius);
        sphere.addColorStop(0, '#fff'); sphere.addColorStop(0.12, color); sphere.addColorStop(1, '#06101b');
        ctx.fillStyle = sphere; ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = isRoot ? '#a5f3fc' : `${color}cc`; ctx.lineWidth = isRoot ? 2.2 : 1; ctx.stroke();
        if (isRoot || isSelected || isHovered) {
          ctx.font = isRoot ? '600 12px ui-monospace, monospace' : '11px ui-monospace, monospace';
          ctx.fillStyle = 'rgba(241,245,249,.95)'; ctx.textBaseline = 'middle';
          ctx.fillText(isRoot ? `ROOT ${short(node.id)}` : short(node.id), p.x + radius + 8, p.y);
        }
        hits.push({ id: node.id, x: p.x, y: p.y, r: radius + 6 });
      });
      hitRef.current = hits;
      animationRef.current = requestAnimationFrame(draw);
    };

    animationRef.current = requestAnimationFrame(draw);
    return () => { stopped = true; cancelAnimationFrame(animationRef.current); };
  }, [graph, selected, hovered, expanded, nodeContext]);

  const point = event => { const rect = canvasRef.current.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; };
  const hitAt = event => { const p = point(event); return [...hitRef.current].reverse().find(hit => Math.hypot(p.x - hit.x, p.y - hit.y) <= hit.r); };
  const focusNode = id => {
    const node = graph.nodeMap.get(id); if (!node) return;
    setSelected(id); cameraRef.current.targetFocus = [node.x, node.y, node.z]; cameraRef.current.targetZoom = Math.max(cameraRef.current.targetZoom, 0.9);
  };
  const onPointerDown = event => {
    const hit = hitAt(event); if (hit) { focusNode(hit.id); return; }
    dragRef.current = { x: event.clientX, y: event.clientY, yaw: cameraRef.current.yaw, pitch: cameraRef.current.pitch };
  };
  const onPointerMove = event => {
    if (dragRef.current) {
      const dx = event.clientX - dragRef.current.x, dy = event.clientY - dragRef.current.y;
      cameraRef.current.yaw = dragRef.current.yaw + dx * 0.006;
      cameraRef.current.pitch = clamp(dragRef.current.pitch + dy * 0.0045, -0.9, 0.9);
      return;
    }
    const hit = hitAt(event); setHovered(hit?.id || '');
  };
  const search = () => { const q = query.trim().toLowerCase(); if (!q) return; const node = graph.nodes.find(item => item.id.includes(q)); if (node) focusNode(node.id); };
  const metric = selected ? graph.metrics.get(selected) : null;

  return <section className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#050a12] shadow-2xl">
    <div className="border-b border-white/[0.06] bg-[#080e18]/90 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[.2em] text-cyan-300">Bubble investigation map</p><h2 className="mt-2 text-xl font-semibold text-white">Large wallet network</h2><p className="mt-2 max-w-3xl text-sm text-slate-400">Adaptive multi-ring layout for dense investigations. Large networks are spread across the full canvas instead of being compressed into one fixed radius.</p></div><div className="flex gap-2 text-xs"><span className="rounded-full border border-cyan-400/20 bg-cyan-400/[.06] px-3 py-1 text-cyan-200">{graph.nodes.length} bubbles</span><span className="rounded-full border border-violet-400/20 bg-violet-400/[.06] px-3 py-1 text-violet-200">{graph.edges.length} links</span></div></div>
      <div className="mt-4 flex flex-wrap gap-2"><input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') search(); }} placeholder="Find wallet…" className="soft-input min-w-[260px] flex-1"/><button type="button" onClick={search} className="secondary-button">Focus</button><button type="button" onClick={() => { setSelected(''); cameraRef.current.yaw = 0.08; cameraRef.current.pitch = -0.05; fitCamera(); }} className="secondary-button">Fit map</button></div>
    </div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="relative min-h-[640px] overflow-hidden"><canvas ref={canvasRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { dragRef.current = null; }} onPointerLeave={() => { if (!dragRef.current) setHovered(''); }} onWheel={event => { event.preventDefault(); cameraRef.current.targetZoom = clamp(cameraRef.current.targetZoom * (event.deltaY > 0 ? 0.88 : 1.12), 0.18, 2.4); }} className="h-[640px] w-full touch-none cursor-grab outline-none active:cursor-grabbing lg:h-[760px]"/><div className="pointer-events-none absolute left-4 top-4 rounded-full border border-cyan-400/15 bg-[#04101d]/85 px-3 py-1.5 text-[10px] uppercase tracking-[.17em] text-cyan-200">Adaptive dense mode · drag orbit · wheel zoom · click bubble</div></div>
      <aside className="space-y-4 border-t border-white/[0.06] bg-[#080e18] p-5 lg:border-l lg:border-t-0"><h3 className="text-lg font-semibold text-white">Wallet details</h3>{selected ? <><p className="break-all font-mono text-sm text-cyan-300">{selected}</p><div className="grid grid-cols-2 gap-2"><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Transfers</p><p className="mt-1 text-2xl font-semibold text-white">{metric?.transfers || 0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Peers</p><p className="mt-1 text-2xl font-semibold text-white">{metric?.peers?.size || 0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Incoming</p><p className="mt-1 text-2xl font-semibold text-white">{metric?.incoming || 0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Outgoing</p><p className="mt-1 text-2xl font-semibold text-white">{metric?.outgoing || 0}</p></div></div>{onExpandAddress && selected !== graph.root && !expanded.has(selected) && <button type="button" onClick={() => onExpandAddress(selected)} disabled={Boolean(expandingAddress)} className="primary-button w-full">{normalized(expandingAddress) === selected ? 'Expanding…' : 'Expand one observed hop'}</button>}<a href={`https://etherscan.io/address/${selected}`} target="_blank" rel="noreferrer" className="secondary-button block text-center">Etherscan ↗</a></> : <div className="rounded-2xl border border-slate-800 bg-slate-950/45 p-4 text-sm leading-6 text-slate-400">Dense mode is active because this investigation contains many wallets. Click any bubble to inspect it.</div>}<div className="border-t border-white/[0.06] pt-4 text-xs leading-5 text-slate-600">The layout is deterministic and visual only. Ring position does not imply ownership, taint, or intent.</div></aside>
    </div>
  </section>;
}

export default function ScalableBubbleInvestigationGraph(props) {
  const uniqueCount = useMemo(() => new Set((props.transactions || []).flatMap(tx => [normalized(tx.from_address), normalized(tx.to_address)]).filter(Boolean)).size, [props.transactions]);
  if (uniqueCount <= 90) return <BubbleInvestigationGraph {...props} />;
  return <DenseBubbleGraph {...props} />;
}
