import { useEffect, useMemo, useRef, useState } from 'react';

const normalized = value => String(value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const COLORS = ['#38bdf8','#a78bfa','#34d399','#f59e0b','#fb7185','#2dd4bf','#60a5fa','#e879f9','#facc15','#4ade80'];

function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function numeric(value) { const n = Number(value); return Number.isFinite(n) ? Math.abs(n) : 0; }
function timestamp(tx) {
  const raw = tx.timestamp || tx.time || tx.block_time || tx.datetime;
  if (!raw) return null;
  if (typeof raw === 'number') return raw > 1e12 ? raw : raw * 1000;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}
function assetName(tx) { return String(tx.asset || (tx.category === 'erc20' ? 'TOKEN' : 'ETH')).toUpperCase(); }
function nodeKind(labels = []) {
  const text = labels.map(label => `${label.entity_name || ''} ${label.entity_id || ''} ${label.category || ''}`).join(' ').toLowerCase();
  if (/exchange|binance|coinbase|kraken|okx|bybit|cex/.test(text)) return 'exchange';
  if (/uniswap|aave|lido|dex|router|factory|swap/.test(text)) return 'protocol';
  if (/token|usdc|usdt|link|steth|wsteth/.test(text)) return 'token';
  if (/contract|market|vault|pool/.test(text)) return 'contract';
  return 'wallet';
}

function buildGraph(transactions, rootAddress, nodeContext) {
  const root = normalized(rootAddress);
  const edges = transactions.filter(tx => tx.from_address && tx.to_address && tx.hash).map((tx, index) => ({
    id: `${tx.hash}-${tx.category || tx.asset || 'tx'}-${index}`,
    from: normalized(tx.from_address),
    to: normalized(tx.to_address),
    tx,
    value: numeric(tx.value),
    asset: assetName(tx),
    risk: Number(tx.risk_score || 0),
    time: timestamp(tx),
  }));
  const ids = [...new Set(edges.flatMap(edge => [edge.from, edge.to]))];
  if (root && !ids.includes(root)) ids.unshift(root);

  const adjacency = new Map(ids.map(id => [id, []]));
  edges.forEach(edge => {
    adjacency.get(edge.from)?.push({ id: edge.to, edge });
    adjacency.get(edge.to)?.push({ id: edge.from, edge });
  });

  // BFS makes the root visually meaningful instead of placing all addresses arbitrarily.
  const hop = new Map([[root, 0]]);
  const branch = new Map([[root, root]]);
  const queue = root ? [root] : [];
  for (let i = 0; i < queue.length; i += 1) {
    const current = queue[i];
    for (const next of adjacency.get(current) || []) {
      if (hop.has(next.id)) continue;
      hop.set(next.id, (hop.get(current) || 0) + 1);
      branch.set(next.id, current === root ? next.id : branch.get(current));
      queue.push(next.id);
    }
  }
  ids.forEach(id => {
    if (!hop.has(id)) { hop.set(id, 3); branch.set(id, id); }
  });

  const branchIds = [...new Set(ids.filter(id => id !== root).map(id => branch.get(id)))];
  const branchIndex = new Map(branchIds.map((id, index) => [id, index]));
  const perHop = new Map();
  ids.forEach(id => {
    const h = hop.get(id) || 0;
    if (!perHop.has(h)) perHop.set(h, []);
    perHop.get(h).push(id);
  });

  const nodes = ids.map(id => {
    const h = hop.get(id) || 0;
    const labels = nodeContext[id]?.entityLabels || [];
    const siblings = perHop.get(h) || [id];
    const index = siblings.indexOf(id);
    if (id === root) return { id, x: 0, y: 0, z: 0, hop: 0, cluster: -1, labels, kind: 'root' };
    const b = branchIndex.get(branch.get(id)) ?? index;
    const branchAngle = (b / Math.max(1, branchIds.length)) * Math.PI * 2;
    const ringOffset = (index / Math.max(1, siblings.length)) * Math.PI * 2;
    const jitter = ((hash(id) % 1000) / 1000 - .5) * .42;
    const angle = branchAngle * .72 + ringOffset * .28 + jitter;
    const radius = h === 1 ? 105 : h === 2 ? 185 : 250 + Math.min(70, (h - 3) * 28);
    const z = Math.sin(angle * 1.7 + jitter) * (h === 1 ? 34 : h === 2 ? 62 : 88);
    return {
      id,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius * .70,
      z,
      hop: h,
      cluster: b,
      labels,
      kind: nodeKind(labels),
    };
  });
  const nodeMap = new Map(nodes.map(node => [node.id, node]));

  // A short collision pass keeps bubbles compact without collapsing them.
  for (let tick = 0; tick < 32; tick += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      if (a.id === root) continue;
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        if (b.id === root) continue;
        let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const distance = Math.max(1, Math.sqrt(dx*dx + dy*dy + dz*dz));
        const target = 42;
        if (distance >= target) continue;
        const push = (target - distance) * .10;
        dx /= distance; dy /= distance; dz /= distance;
        a.x += dx * push; a.y += dy * push; a.z += dz * push;
        b.x -= dx * push; b.y -= dy * push; b.z -= dz * push;
      }
    }
  }

  const metrics = new Map(nodes.map(node => [node.id, { incoming: 0, outgoing: 0, transfers: 0, peers: new Set(), assets: new Set(), volume: 0, maxRisk: Number(nodeContext[node.id]?.maxRisk || 0) }]));
  edges.forEach(edge => {
    const from = metrics.get(edge.from), to = metrics.get(edge.to);
    if (from) { from.outgoing += 1; from.transfers += 1; from.peers.add(edge.to); from.assets.add(edge.asset); from.volume += edge.value; from.maxRisk = Math.max(from.maxRisk, edge.risk); }
    if (to) { to.incoming += 1; to.transfers += 1; to.peers.add(edge.from); to.assets.add(edge.asset); to.volume += edge.value; to.maxRisk = Math.max(to.maxRisk, edge.risk); }
  });

  return { root, nodes, nodeMap, edges, metrics, branchCount: branchIds.length };
}

function rotatePoint(node, camera) {
  const cy = Math.cos(camera.yaw), sy = Math.sin(camera.yaw), cp = Math.cos(camera.pitch), sp = Math.sin(camera.pitch);
  const x1 = node.x * cy + node.z * sy;
  const z1 = -node.x * sy + node.z * cy;
  return { x: x1, y: node.y * cp - z1 * sp, z: node.y * sp + z1 * cp };
}
function projectNode(node, camera, width, height) {
  const p = rotatePoint(node, camera);
  const depth = Math.max(320, 820 - p.z);
  const perspective = 820 / depth;
  return {
    x: width / 2 + p.x * perspective * camera.zoom,
    y: height / 2 + p.y * perspective * camera.zoom,
    z: p.z,
    perspective,
  };
}
function segmentDistance(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, length2 = dx*dx + dy*dy;
  if (!length2) return Math.hypot(px-ax, py-ay);
  const t = clamp(((px-ax)*dx + (py-ay)*dy) / length2, 0, 1);
  return Math.hypot(px-(ax+t*dx), py-(ay+t*dy));
}
function nodeColor(node, metric, context, selected, root, expanded) {
  if (node.id === root) return '#38d6f4';
  if (selected) return '#ffd166';
  if (expanded.has(node.id)) return '#f59e0b';
  if ((context.entityLabels || []).length) return '#34d399';
  if (Number(metric?.maxRisk || 0) >= 70) return '#fb7185';
  return COLORS[(node.cluster < 0 ? 0 : node.cluster) % COLORS.length];
}

export default function BubbleInvestigationGraph({ transactions = [], rootAddress = '', onExpandAddress, expandingAddress = '', expandedAddresses = [], nodeContext = {} }) {
  const canvasRef = useRef(null);
  const projectedRef = useRef(new Map());
  const animationRef = useRef(null);
  const dragRef = useRef(null);
  const cameraRef = useRef({ yaw: .18, pitch: -.10, zoom: 1 });
  const [selectedNode, setSelectedNode] = useState('');
  const [selectedEdge, setSelectedEdge] = useState('');
  const [asset, setAsset] = useState('ALL');
  const [timeWindow, setTimeWindow] = useState('ALL');
  const [minRisk, setMinRisk] = useState(0);
  const [query, setQuery] = useState('');
  const [isolate, setIsolate] = useState(false);
  const [replay, setReplay] = useState(100);
  const [viewVersion, setViewVersion] = useState(0);

  const expanded = useMemo(() => new Set(expandedAddresses.map(normalized)), [expandedAddresses]);
  const graph = useMemo(() => buildGraph(transactions, rootAddress, nodeContext), [transactions, rootAddress, nodeContext]);
  const assets = useMemo(() => ['ALL', ...[...new Set(graph.edges.map(edge => edge.asset))].sort()], [graph]);
  const timestamped = useMemo(() => graph.edges.map(edge => edge.time).filter(Boolean).sort((a,b)=>a-b), [graph]);
  const oldest = timestamped[0] || 0, newest = timestamped[timestamped.length - 1] || 0;
  const replayCutoff = oldest && newest ? oldest + (newest-oldest)*(replay/100) : 0;

  const filteredEdges = useMemo(() => {
    const windows = { '24H': 86400000, '7D': 604800000, '30D': 2592000000 };
    const cutoff = timeWindow === 'ALL' || !newest ? 0 : newest - windows[timeWindow];
    return graph.edges.filter(edge => {
      if (asset !== 'ALL' && edge.asset !== asset) return false;
      if (edge.risk < Number(minRisk || 0)) return false;
      if (cutoff && edge.time && edge.time < cutoff) return false;
      if (replayCutoff && edge.time && edge.time > replayCutoff) return false;
      if (isolate && selectedNode && edge.from !== selectedNode && edge.to !== selectedNode) return false;
      return true;
    });
  }, [graph, asset, minRisk, timeWindow, newest, replayCutoff, isolate, selectedNode]);
  const visibleIds = useMemo(() => new Set(filteredEdges.flatMap(edge => [edge.from, edge.to]).concat(graph.root ? [graph.root] : [])), [filteredEdges, graph.root]);
  const visibleNodes = useMemo(() => graph.nodes.filter(node => visibleIds.has(node.id)), [graph, visibleIds]);

  // Auto-fit every meaningful scene change. This is the key fix for the off-camera failure.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !visibleNodes.length) return;
    const width = canvas.clientWidth || 900, height = canvas.clientHeight || 620;
    const maxRadius = Math.max(90, ...visibleNodes.map(node => Math.hypot(node.x, node.y) + 35));
    cameraRef.current.zoom = clamp(Math.min(width, height) * .38 / maxRadius, .72, 2.25);
    cameraRef.current.yaw = .18;
    cameraRef.current.pitch = -.10;
    setViewVersion(version => version + 1);
  }, [visibleNodes.length, graph.edges.length, asset, timeWindow, replay, isolate]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return undefined;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let stopped = false;

    const draw = time => {
      if (stopped) return;
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
      const pixelWidth = Math.floor(width*dpr), pixelHeight = Math.floor(height*dpr);
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
      ctx.setTransform(dpr,0,0,dpr,0,0);

      const bg = ctx.createRadialGradient(width*.50,height*.46,20,width*.50,height*.46,Math.max(width,height)*.72);
      bg.addColorStop(0,'#10223b'); bg.addColorStop(.45,'#07111f'); bg.addColorStop(1,'#03070d');
      ctx.fillStyle = bg; ctx.fillRect(0,0,width,height);

      // subtle star/grid points give depth without noise
      ctx.fillStyle = 'rgba(56,189,248,.08)';
      for (let x=28;x<width;x+=46) for (let y=30;y<height;y+=46) ctx.fillRect(x,y,1,1);

      const projected = new Map();
      visibleNodes.forEach(node => projected.set(node.id, projectNode(node,cameraRef.current,width,height)));
      projectedRef.current = projected;

      const sortedEdges = [...filteredEdges].sort((a,b) => ((projected.get(a.from)?.z||0)+(projected.get(a.to)?.z||0))-((projected.get(b.from)?.z||0)+(projected.get(b.to)?.z||0)));
      sortedEdges.forEach(edge => {
        const a=projected.get(edge.from), b=projected.get(edge.to); if(!a||!b)return;
        const active = edge.id === selectedEdge;
        const token = edge.tx.category === 'erc20';
        ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
        ctx.strokeStyle = active ? 'rgba(251,191,36,.95)' : token ? 'rgba(167,139,250,.48)' : 'rgba(125,211,252,.30)';
        ctx.lineWidth = active ? 3 : 1.25;
        if (token) ctx.setLineDash([6,5]); else ctx.setLineDash([]);
        ctx.stroke();

        const t = (time*.00013 + (hash(edge.id)%1000)/1000) % 1;
        const px=a.x+(b.x-a.x)*t, py=a.y+(b.y-a.y)*t;
        ctx.beginPath(); ctx.arc(px,py,active?3.2:2.0,0,Math.PI*2);
        ctx.fillStyle = active ? '#fde68a' : token ? '#c4b5fd' : '#7dd3fc'; ctx.fill();
      });
      ctx.setLineDash([]);

      const sortedNodes = [...visibleNodes].sort((a,b)=>(projected.get(a.id)?.z||0)-(projected.get(b.id)?.z||0));
      sortedNodes.forEach(node => {
        const point=projected.get(node.id), metric=graph.metrics.get(node.id), context=nodeContext[node.id]||{}; if(!point)return;
        const activity = Math.log2(1+(metric?.transfers||0));
        const base = node.id===graph.root ? 27 : 14 + activity*3.4 + (context.entityLabels?.length?3:0);
        const radius = clamp(base*clamp(point.perspective,.72,1.45),10,38);
        const color=nodeColor(node,metric,context,node.id===selectedNode,graph.root,expanded);

        const glow=ctx.createRadialGradient(point.x,point.y,0,point.x,point.y,radius*2.0);
        glow.addColorStop(0,`${color}55`); glow.addColorStop(.52,`${color}20`); glow.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=glow; ctx.beginPath();ctx.arc(point.x,point.y,radius*2,0,Math.PI*2);ctx.fill();

        const bubble=ctx.createRadialGradient(point.x-radius*.32,point.y-radius*.36,radius*.08,point.x,point.y,radius);
        bubble.addColorStop(0,'#ffffff'); bubble.addColorStop(.12,color); bubble.addColorStop(.58,`${color}d9`); bubble.addColorStop(1,'#06101c');
        ctx.fillStyle=bubble; ctx.beginPath();ctx.arc(point.x,point.y,radius,0,Math.PI*2);ctx.fill();
        ctx.strokeStyle = node.id===selectedNode ? '#fde68a' : node.id===graph.root ? '#a5f3fc' : `${color}cc`;
        ctx.lineWidth=node.id===graph.root?3:node.id===selectedNode?3:1.5;ctx.stroke();

        if (node.id===graph.root || node.id===selectedNode || (metric?.transfers||0)>=4) {
          ctx.font = node.id===graph.root ? '600 12px ui-monospace, SFMono-Regular, Menlo, monospace' : '11px ui-monospace, SFMono-Regular, Menlo, monospace';
          ctx.fillStyle='rgba(226,232,240,.92)';
          ctx.textAlign='left'; ctx.textBaseline='middle';
          ctx.fillText(node.id===graph.root?`ROOT ${short(node.id)}`:short(node.id),point.x+radius+7,point.y);
        }
      });
      animationRef.current=requestAnimationFrame(draw);
    };
    animationRef.current=requestAnimationFrame(draw);
    return()=>{stopped=true;cancelAnimationFrame(animationRef.current);};
  },[filteredEdges,visibleNodes,selectedNode,selectedEdge,graph,nodeContext,expanded,viewVersion]);

  const chooseNode = id => { setSelectedNode(id); setSelectedEdge(''); };
  const search = () => {
    const q=query.trim().toLowerCase(); if(!q)return;
    const node=graph.nodes.find(item=>item.id.includes(q)||(nodeContext[item.id]?.entityLabels||[]).some(label=>String(label.entity_name||label.entity_id||'').toLowerCase().includes(q)));
    if(node)chooseNode(node.id);
  };
  const pointerDown = event => { if(event.button!==0)return; dragRef.current={x:event.clientX,y:event.clientY,yaw:cameraRef.current.yaw,pitch:cameraRef.current.pitch,moved:false}; event.currentTarget.setPointerCapture?.(event.pointerId); };
  const pointerMove = event => { const drag=dragRef.current;if(!drag)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)drag.moved=true;cameraRef.current.yaw=drag.yaw+dx*.008;cameraRef.current.pitch=clamp(drag.pitch+dy*.006,-1.0,1.0);setViewVersion(v=>v+1); };
  const pointerUp = event => {
    const drag=dragRef.current;dragRef.current=null;if(!drag||drag.moved)return;
    const rect=event.currentTarget.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
    let pickedNode='',bestNode=42;
    projectedRef.current.forEach((p,id)=>{const d=Math.hypot(p.x-x,p.y-y);if(d<bestNode){bestNode=d;pickedNode=id;}});
    if(pickedNode){chooseNode(pickedNode);return;}
    let pickedEdge='',bestEdge=9;
    filteredEdges.forEach(edge=>{const a=projectedRef.current.get(edge.from),b=projectedRef.current.get(edge.to);if(!a||!b)return;const d=segmentDistance(x,y,a.x,a.y,b.x,b.y);if(d<bestEdge){bestEdge=d;pickedEdge=edge.id;}});
    if(pickedEdge){setSelectedEdge(pickedEdge);setSelectedNode('');}
  };
  const wheel = event => { event.preventDefault(); cameraRef.current.zoom=clamp(cameraRef.current.zoom*(event.deltaY>0?.90:1.10),.55,3.2);setViewVersion(v=>v+1); };
  const reset = () => { setSelectedNode('');setSelectedEdge('');setIsolate(false);setReplay(100);cameraRef.current.yaw=.18;cameraRef.current.pitch=-.10;const canvas=canvasRef.current;if(canvas){const maxRadius=Math.max(90,...visibleNodes.map(node=>Math.hypot(node.x,node.y)+35));cameraRef.current.zoom=clamp(Math.min(canvas.clientWidth||900,canvas.clientHeight||620)*.38/maxRadius,.72,2.25);}setViewVersion(v=>v+1); };

  const selectedMetric = selectedNode ? graph.metrics.get(selectedNode) : null;
  const selectedContext = selectedNode ? nodeContext[selectedNode] || {} : {};
  const selectedRecord = selectedEdge ? graph.edges.find(edge=>edge.id===selectedEdge) : null;

  return <section className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/70">
    <div className="border-b border-slate-800 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="eyebrow text-cyan-300">3D bubble investigation</p><h2 className="mt-2 text-xl font-semibold text-white">Wallet relationship map</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Root-centered bubble map. Distance shows graph hops and branch grouping; bubble size emphasizes observed activity. It is a visual investigation aid, not an ownership claim.</p></div>
        <div className="flex flex-wrap gap-2 text-xs"><span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">{visibleNodes.length} bubbles</span><span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{filteredEdges.length} transfers</span><span className="status-pill border-slate-700 bg-slate-900 text-slate-300">{graph.branchCount} root branches</span></div>
      </div>
      <div className="mt-4 grid gap-2 lg:grid-cols-[minmax(240px,1fr)_160px_150px_170px_auto]">
        <div className="flex gap-2"><input className="soft-input min-w-0 flex-1" value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Enter')search();}} placeholder="Find wallet or entity…" aria-label="Find wallet or entity"/><button type="button" onClick={search} className="secondary-button">Focus</button></div>
        <select className="soft-input" value={asset} onChange={event=>setAsset(event.target.value)} aria-label="Asset filter">{assets.map(item=><option key={item} value={item}>{item==='ALL'?'All assets':item}</option>)}</select>
        <select className="soft-input" value={timeWindow} onChange={event=>setTimeWindow(event.target.value)} aria-label="Time window"><option value="ALL">All time</option><option value="24H">24 hours</option><option value="7D">7 days</option><option value="30D">30 days</option></select>
        <label className="rounded-lg border border-slate-700 bg-slate-950/45 px-3 py-2 text-xs text-slate-400">Risk ≥ {minRisk}<input type="range" min="0" max="100" value={minRisk} onChange={event=>setMinRisk(Number(event.target.value))} className="mt-1 w-full" aria-label="Minimum risk"/></label>
        <button type="button" onClick={reset} className="secondary-button">Fit map</button>
      </div>
      {timestamped.length>1&&<div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2"><div className="flex justify-between text-[11px] text-slate-500"><span>Time replay</span><span>{replay===100?'Latest loaded evidence':new Date(replayCutoff).toLocaleString()}</span></div><input type="range" min="0" max="100" value={replay} onChange={event=>setReplay(Number(event.target.value))} className="mt-1 w-full" aria-label="Time replay position"/></div>}
    </div>

    <div className="grid lg:grid-cols-[minmax(0,1fr)_330px]">
      <div className="relative min-h-[560px] overflow-hidden">
        <canvas ref={canvasRef} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{dragRef.current=null;}} onWheel={wheel} className="h-[560px] w-full touch-none cursor-grab outline-none active:cursor-grabbing lg:h-[680px]" tabIndex={0} aria-label="Interactive 3D bubble map. Drag to orbit, wheel to zoom, click bubbles or transfer lines."/>
        <div className="pointer-events-none absolute left-4 top-4 rounded-full border border-cyan-400/20 bg-[#04101d]/85 px-3 py-1.5 text-[10px] uppercase tracking-[.17em] text-cyan-200">Drag orbit · wheel zoom · click bubble/edge</div>
        <div className="pointer-events-none absolute bottom-4 left-4 flex flex-wrap gap-2 text-[10px] text-slate-400"><span className="text-cyan-300">● root</span><span className="text-emerald-300">● labeled</span><span className="text-rose-300">● high risk</span><span className="text-amber-300">● expanded/selected</span><span>solid ETH · dashed token</span></div>
      </div>
      <aside className="space-y-4 border-t border-slate-800 p-5 lg:border-l lg:border-t-0">
        <div className="flex items-center justify-between"><h3 className="font-semibold text-white">Selected evidence</h3>{selectedNode&&<button type="button" onClick={()=>setIsolate(value=>!value)} className="text-xs text-cyan-300 underline">{isolate?'Show all':'Isolate'}</button>}</div>
        {selectedNode?<>
          <div><p className="text-xs text-slate-500">Wallet</p><p className="mt-1 break-all font-mono text-xs text-cyan-300">{selectedNode}</p></div>
          {selectedNode===graph.root&&<span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">Investigation root</span>}
          <div className="grid grid-cols-2 gap-2"><div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3"><p className="text-xs text-slate-500">Transfers</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.transfers||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3"><p className="text-xs text-slate-500">Peers</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.peers?.size||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3"><p className="text-xs text-slate-500">Incoming</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.incoming||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3"><p className="text-xs text-slate-500">Max risk</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.maxRisk||0}</p></div></div>
          {(selectedContext.entityLabels||[]).map((label,index)=><div key={`${label.source}-${index}`} className="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><p className="font-medium text-emerald-200">{label.entity_name||label.entity_id}</p><p className="mt-1 text-xs text-slate-400">Source: {label.source}</p></div>)}
          {selectedMetric?.assets?.size>0&&<p className="text-xs text-slate-400">Assets: {[...selectedMetric.assets].slice(0,8).join(', ')}</p>}
          {onExpandAddress&&selectedNode!==graph.root&&!expanded.has(selectedNode)&&<button type="button" onClick={()=>onExpandAddress(selectedNode)} disabled={Boolean(expandingAddress)} className="primary-button w-full disabled:opacity-50">{normalized(expandingAddress)===selectedNode?'Expanding…':'Expand one observed hop'}</button>}
          <a href={`https://etherscan.io/address/${selectedNode}`} target="_blank" rel="noreferrer" className="text-sm text-cyan-300 underline">Verify wallet on Etherscan ↗</a>
        </>:selectedRecord?<><p className="text-xs text-slate-500">Transfer</p><p className="break-all font-mono text-xs text-slate-300">{selectedRecord.from}</p><p className="text-cyan-300">↓</p><p className="break-all font-mono text-xs text-slate-300">{selectedRecord.to}</p><div className="rounded-xl border border-slate-800 bg-slate-950/45 p-3 text-sm text-slate-300"><p>Asset: <span className="text-white">{selectedRecord.asset}</span></p><p className="mt-1">Value: <span className="text-white">{selectedRecord.tx.value??'—'}</span></p><p className="mt-1">Risk: <span className="text-white">{selectedRecord.risk}</span></p></div><a href={selectedRecord.tx.evidence_url||`https://etherscan.io/tx/${selectedRecord.tx.hash}`} target="_blank" rel="noreferrer" className="text-sm text-cyan-300 underline">Verify transaction ↗</a></>:<div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm leading-6 text-slate-400">The complete loaded network should now be visible immediately. Select a bubble to inspect it, or drag the map to see depth.</div>}
        <div className="border-t border-slate-800 pt-4 text-xs leading-5 text-slate-500">Spatial grouping reflects observed graph hops/branches only. It does not prove common control, ownership, taint, or complete transaction history.</div>
      </aside>
    </div>
  </section>;
}
