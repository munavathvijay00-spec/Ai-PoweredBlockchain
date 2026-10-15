import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-5)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const COLORS = {
  root: '#22d3ee',
  high: '#fb7185',
  medium: '#fbbf24',
  normal: '#60a5fa',
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
    return nodes.get(key);
  }

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;

    const value = numericValue(tx.value);
    const asset = tx.asset || 'ETH';
    const key = `${source}|${target}|${asset}`;

    if (!byPair.has(key)) {
      byPair.set(key, {
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

    const edge = byPair.get(key);
    edge.totalValue += value;
    edge.txCount += 1;
    if (tx.risk_score != null) {
      edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);
    }
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
  const others = list
    .filter(node => node.id !== rootId)
    .sort((a, b) => b.txCount - a.txCount);

  const positioned = [];
  if (rootNode) {
    positioned.push({ ...rootNode, depth: 0, x: 0, y: 0, z: 0, isRoot: true });
  }

  const byDepth = new Map();
  for (const node of others) {
    const d = depth.get(node.id) ?? 2;
    if (!byDepth.has(d)) byDepth.set(d, []);
    byDepth.get(d).push(node);
  }

  for (const [d, group] of [...byDepth.entries()].sort((a, b) => a[0] - b[0])) {
    const shellRadius = 205 + Math.max(0, d - 1) * 185;
    const n = group.length;
    group.forEach((node, index) => {
      const y = 1 - (index / Math.max(1, n - 1)) * 2;
      const radial = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = index * Math.PI * (3 - Math.sqrt(5)) + d * 0.67;
      positioned.push({
        ...node,
        depth: d,
        x: Math.cos(theta) * radial * shellRadius,
        y: y * shellRadius * 0.84,
        z: Math.sin(theta) * radial * shellRadius,
        isRoot: false,
      });
    });
  }

  if (!rootNode) {
    list.forEach((node, index) => {
      const n = Math.max(1, list.length);
      const y = 1 - (index / Math.max(1, n - 1)) * 2;
      const radial = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = index * Math.PI * (3 - Math.sqrt(5));
      const radius = 300;
      positioned.push({
        ...node,
        depth: 1,
        x: Math.cos(theta) * radial * radius,
        y: y * radius * 0.82,
        z: Math.sin(theta) * radial * radius,
        isRoot: false,
      });
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
  const cosy = Math.cos(yaw);
  const siny = Math.sin(yaw);
  const x1 = point.x * cosy - point.z * siny;
  const z1 = point.x * siny + point.z * cosy;
  const cosp = Math.cos(pitch);
  const sinp = Math.sin(pitch);
  return {
    x: x1,
    y: point.y * cosp - z1 * sinp,
    z: point.y * sinp + z1 * cosp,
  };
}

function project(point, width, height, yaw, pitch, zoom) {
  const rotated = rotate(point, yaw, pitch);
  const camera = 1050;
  const depth = camera + rotated.z;
  const scale = clamp((camera / Math.max(300, depth)) * zoom, 0.18, 4.6);
  return {
    x: width / 2 + rotated.x * scale,
    y: height / 2 + rotated.y * scale,
    z: rotated.z,
    scale,
  };
}

function drawSphere(ctx, x, y, radius, color, selected, root) {
  const glow = selected ? 34 : root ? 26 : 16;
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur = glow;

  const body = ctx.createRadialGradient(
    x - radius * 0.34,
    y - radius * 0.38,
    Math.max(1, radius * 0.08),
    x,
    y,
    radius,
  );
  body.addColorStop(0, '#ffffff');
  body.addColorStop(0.12, color);
  body.addColorStop(0.52, color);
  body.addColorStop(1, '#06101d');

  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.strokeStyle = selected ? '#ffffff' : color;
  ctx.globalAlpha = selected ? 0.96 : 0.78;
  ctx.lineWidth = selected ? 2.2 : 1;
  ctx.beginPath();
  ctx.arc(x, y, radius - 0.5, 0, Math.PI * 2);
  ctx.stroke();

  ctx.globalAlpha = 0.34;
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.arc(x - radius * 0.3, y - radius * 0.34, Math.max(1.2, radius * 0.13), 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

export default function FlowGraph3D({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });

  const [yaw, setYaw] = useState(-0.42);
  const [pitch, setPitch] = useState(0.16);
  const [zoom, setZoom] = useState(0.88);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState('');
  const [minValue, setMinValue] = useState(0);
  const [maxDepth, setMaxDepth] = useState(3);
  const [showParticles, setShowParticles] = useState(true);
  const [mode, setMode] = useState('3d');

  const network = useMemo(() => aggregate(transactions, root), [transactions, root]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const allowedNodes = new Set(
      network.nodes
        .filter(node => node.depth <= maxDepth && (!q || node.id.includes(q)))
        .map(node => node.id),
    );

    const matchingEdges = network.edges.filter(edge => {
      if (edge.totalValue < Number(minValue || 0)) return false;
      const sourceNode = network.nodes.find(node => node.id === edge.source);
      const targetNode = network.nodes.find(node => node.id === edge.target);
      if ((sourceNode?.depth ?? 9) > maxDepth || (targetNode?.depth ?? 9) > maxDepth) return false;
      if (!q) return true;
      return edge.source.includes(q)
        || edge.target.includes(q)
        || edge.transactions.some(tx => String(tx.hash).toLowerCase().includes(q));
    });

    if (q) {
      matchingEdges.forEach(edge => {
        allowedNodes.add(edge.source);
        allowedNodes.add(edge.target);
      });
    }

    return {
      nodes: network.nodes.filter(node => allowedNodes.has(node.id)),
      edges: matchingEdges,
    };
  }, [network, query, minValue, maxDepth]);

  const selectedNode = selected?.kind === 'node'
    ? network.nodes.find(node => node.id === selected.id)
    : null;
  const selectedEdge = selected?.kind === 'edge'
    ? network.edges.find(edge => edge.id === selected.id)
    : null;

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

      const bg = ctx.createRadialGradient(
        width * 0.48,
        height * 0.46,
        50,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.72,
      );
      bg.addColorStop(0, '#15233a');
      bg.addColorStop(0.56, '#0a1323');
      bg.addColorStop(1, '#040914');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, width, height);

      ctx.globalAlpha = 0.18;
      for (let i = 0; i < 70; i += 1) {
        const sx = (i * 97) % width;
        const sy = (i * 53) % height;
        const r = (i % 3) * 0.45 + 0.35;
        ctx.fillStyle = i % 7 === 0 ? '#22d3ee' : '#94a3b8';
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      const projection = new Map();
      filtered.nodes.forEach(node => {
        projection.set(node.id, project(node, width, height, yaw, pitch, zoom));
      });

      const edgeHits = [];
      const maxEdge = Math.max(1, ...filtered.edges.map(edge => edge.totalValue));

      [...filtered.edges]
        .sort((a, b) => {
          const az = Math.min(projection.get(a.source)?.z ?? 0, projection.get(a.target)?.z ?? 0);
          const bz = Math.min(projection.get(b.source)?.z ?? 0, projection.get(b.target)?.z ?? 0);
          return az - bz;
        })
        .forEach((edge, edgeIndex) => {
          const a = projection.get(edge.source);
          const b = projection.get(edge.target);
          if (!a || !b) return;

          const isActive = selectedEdge?.id === edge.id;
          const ratio = Math.log10(edge.totalValue + 1) / Math.log10(maxEdge + 1 || 2);
          const avgScale = (a.scale + b.scale) / 2;

          ctx.save();
          ctx.strokeStyle = isActive ? '#ffffff' : '#94a3b8';
          ctx.globalAlpha = isActive ? 0.94 : 0.18 + ratio * 0.32;
          ctx.lineWidth = (isActive ? 2.6 : 0.7 + ratio * 2.2) * clamp(avgScale, 0.65, 1.5);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
          ctx.restore();

          if (showParticles) {
            const phase = ((time * 0.00014 * (1 + (edgeIndex % 3) * 0.18)) + edgeIndex * 0.13) % 1;
            const px = a.x + (b.x - a.x) * phase;
            const py = a.y + (b.y - a.y) * phase;
            ctx.save();
            ctx.fillStyle = isActive ? '#ffffff' : '#67e8f9';
            ctx.shadowColor = '#22d3ee';
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.arc(px, py, isActive ? 3.6 : 2.2, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }

          edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
        });

      const nodeHits = [];
      [...filtered.nodes]
        .sort((a, b) => (projection.get(a.id)?.z || 0) - (projection.get(b.id)?.z || 0))
        .forEach(node => {
          const p = projection.get(node.id);
          if (!p) return;

          const activeNode = selectedNode?.id === node.id;
          const color = riskColor(node.maxRisk, node.isRoot);
          const importance = Math.log2(node.txCount + node.counterparties.size + 2);
          const baseRadius = node.isRoot ? 30 : 14 + importance * 4.5;
          const radius = clamp(baseRadius * Math.pow(p.scale, 0.72), 9, node.isRoot ? 54 : 42);

          drawSphere(ctx, p.x, p.y, radius, color, activeNode, node.isRoot);

          if (node.isRoot || activeNode || node.txCount >= 3) {
            ctx.save();
            ctx.font = `${activeNode ? 12 : 11}px ui-monospace, SFMono-Regular, Menlo, monospace`;
            ctx.fillStyle = '#e2e8f0';
            ctx.globalAlpha = activeNode ? 1 : 0.84;
            ctx.shadowColor = '#020617';
            ctx.shadowBlur = 8;
            ctx.fillText(short(node.id), p.x + radius + 8, p.y + 4);
            ctx.restore();
          }

          nodeHits.push({ id: node.id, x: p.x, y: p.y, r: radius + 8 });
        });

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      active = false;
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [filtered, yaw, pitch, zoom, selectedNode?.id, selectedEdge?.id, showParticles, mode]);

  function distanceToSegment(px, py, ax, ay, bx, by) {
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy || 1;
    const t = clamp(((px - ax) * dx + (py - ay) * dy) / len2, 0, 1);
    const x = ax + t * dx;
    const y = ay + t * dy;
    return Math.hypot(px - x, py - y);
  }

  function pointerPosition(event) {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function pointerDown(event) {
    const p = pointerPosition(event);
    const node = [...hitRef.current.nodes]
      .reverse()
      .find(hit => Math.hypot(p.x - hit.x, p.y - hit.y) <= hit.r);

    if (node) {
      setSelected({ kind: 'node', id: node.id });
      return;
    }

    const edge = [...hitRef.current.edges]
      .reverse()
      .find(hit => distanceToSegment(p.x, p.y, hit.ax, hit.ay, hit.bx, hit.by) <= 8);

    if (edge) {
      setSelected({ kind: 'edge', id: edge.id });
      return;
    }

    dragRef.current = { x: event.clientX, y: event.clientY, yaw, pitch };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function pointerMove(event) {
    if (!dragRef.current) return;
    setYaw(dragRef.current.yaw + (event.clientX - dragRef.current.x) * 0.007);
    setPitch(clamp(dragRef.current.pitch + (event.clientY - dragRef.current.y) * 0.006, -1.15, 1.15));
  }

  const relatedEdges = selectedNode
    ? network.edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
    : [];

  const selectedAssetValue = selectedEdge
    ? `${selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${selectedEdge.asset}`
    : '';

  return <section className="overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-950/70 shadow-2xl shadow-black/20">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
      <div>
        <p className="eyebrow">3D flow intelligence</p>
        <h3 className="mt-1 text-lg font-semibold text-white">Interactive fund-flow network</h3>
      </div>
      <div className="text-xs text-slate-400">{filtered.nodes.length} wallets · {filtered.edges.length} aggregated relationships</div>
    </div>

    <div className="grid gap-3 border-b border-slate-800 bg-slate-950/70 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_160px_150px_auto]">
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Wallet or transaction hash…" className="soft-input font-mono text-xs" />
      <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} aria-label="Minimum transfer value" className="soft-input text-xs" placeholder="Min value" />
      <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="soft-input text-xs" aria-label="Maximum hop depth">
        <option value={1}>1 hop</option>
        <option value={2}>2 hops</option>
        <option value={3}>3 hops</option>
        <option value={9}>All loaded</option>
      </select>
      <div className="flex gap-2">
        <button type="button" onClick={() => setMode(mode === '3d' ? 'table' : '3d')} className="secondary-button text-xs">{mode === '3d' ? 'Table' : '3D graph'}</button>
        <button type="button" onClick={() => setShowParticles(value => !value)} className="secondary-button text-xs">Flow {showParticles ? 'on' : 'off'}</button>
      </div>
    </div>

    {mode === '3d' ? <div className="grid lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="relative min-h-[620px] bg-[#050a13]">
        <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
          <button type="button" onClick={() => setZoom(value => clamp(value + 0.14, 0.35, 2.5))} className="secondary-button px-3 py-1.5 text-xs">+</button>
          <button type="button" onClick={() => setZoom(value => clamp(value - 0.14, 0.35, 2.5))} className="secondary-button px-3 py-1.5 text-xs">−</button>
          <button type="button" onClick={() => { setYaw(-0.42); setPitch(0.16); setZoom(0.88); }} className="secondary-button px-3 py-1.5 text-xs">Reset camera</button>
        </div>

        <canvas
          ref={canvasRef}
          className="h-[620px] w-full touch-none cursor-grab active:cursor-grabbing"
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={() => { dragRef.current = null; }}
          onPointerCancel={() => { dragRef.current = null; }}
          onWheel={event => {
            event.preventDefault();
            setZoom(value => clamp(value + (event.deltaY < 0 ? 0.08 : -0.08), 0.35, 2.5));
          }}
        />

        {!filtered.nodes.length && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">No loaded relationships match these filters.</div>}
        <div className="pointer-events-none absolute bottom-3 left-4 rounded-full border border-slate-700 bg-slate-950/75 px-3 py-1.5 text-[11px] text-slate-400">Drag empty space to orbit · wheel to zoom · click a sphere or flow</div>
      </div>

      <aside className="border-t border-slate-800 bg-slate-950/65 p-5 lg:border-l lg:border-t-0">
        <p className="eyebrow">Investigation details</p>
        {!selected && <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-sm leading-6 text-slate-400">Select a wallet sphere or transfer relationship. Sphere size reflects loaded activity; edge thickness reflects observed value; moving particles show direction.</div>}

        {selectedNode && <div className="mt-4 space-y-4">
          <div>
            <p className="text-xs text-slate-500">Wallet</p>
            <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-1 block break-all font-mono text-xs text-cyan-300 hover:underline">{selectedNode.id} ↗</a>
          </div>
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
          <div>
            <p className="mb-2 text-xs font-medium text-slate-300">Observed relationships</p>
            <div className="max-h-48 space-y-2 overflow-auto pr-1">
              {relatedEdges.slice(0, 12).map(edge => <button key={edge.id} type="button" onClick={() => setSelected({ kind: 'edge', id: edge.id })} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-left text-[11px] text-slate-400 hover:border-cyan-500/40"><span className="font-mono text-slate-300">{short(edge.source)} → {short(edge.target)}</span><span className="mt-1 block">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 6 })} {edge.asset} · {edge.txCount} tx</span></button>)}
            </div>
          </div>
        </div>}

        {selectedEdge && <div className="mt-4 space-y-4">
          <div><p className="text-xs text-slate-500">Transfer relationship</p><p className="mt-1 font-mono text-xs text-slate-300">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div>
          <div className="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4"><p className="text-xs text-slate-500">Observed transferred value</p><p className="mt-2 text-2xl font-semibold text-cyan-300">{selectedAssetValue}</p><p className="mt-1 text-xs text-slate-500">Across {selectedEdge.txCount} loaded transaction{selectedEdge.txCount === 1 ? '' : 's'}</p></div>
          <div className="space-y-2 text-xs text-slate-400"><p>From <span className="break-all font-mono text-slate-200">{selectedEdge.source}</span></p><p>To <span className="break-all font-mono text-slate-200">{selectedEdge.target}</span></p><p>Max loaded risk <span className="text-slate-200">{selectedEdge.maxRisk == null ? 'Not assessed' : selectedEdge.maxRisk}</span></p></div>
          <div>
            <p className="mb-2 text-xs font-medium text-slate-300">Evidence transactions</p>
            <div className="max-h-56 space-y-2 overflow-auto pr-1">
              {selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-left hover:border-cyan-500/40"><span className="block font-mono text-[11px] text-cyan-300">{short(tx.hash)} ↗</span><span className="mt-1 block text-[11px] text-slate-500">{tx.value} {tx.asset || ''} · {tx.category || 'transfer'}</span></button>)}
            </div>
          </div>
        </div>}
      </aside>
    </div> : <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="border-b border-slate-800 bg-slate-950 text-slate-500"><tr><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Observed value</th><th className="px-4 py-3">Tx count</th><th className="px-4 py-3">Evidence</th></tr></thead>
        <tbody>{filtered.edges.map(edge => <tr key={edge.id} className="border-b border-slate-900 text-slate-300"><td className="px-4 py-3 font-mono">{short(edge.source)}</td><td className="px-4 py-3 font-mono">{short(edge.target)}</td><td className="px-4 py-3">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {edge.asset}</td><td className="px-4 py-3">{edge.txCount}</td><td className="px-4 py-3"><button type="button" onClick={() => { setSelected({ kind: 'edge', id: edge.id }); setMode('3d'); }} className="text-cyan-300 hover:underline">Inspect</button></td></tr>)}</tbody>
      </table>
    </div>}

    <div className="border-t border-amber-500/10 bg-amber-400/[0.035] px-4 py-3 text-[11px] leading-5 text-amber-200/80">Observed loaded ChainScope evidence only. Sphere size represents loaded activity and aggregated values represent the current transfer sample, not complete lifetime wallet totals.</div>
  </section>;
}
