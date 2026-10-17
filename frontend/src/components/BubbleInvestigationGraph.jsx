import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';

const normalized = value => String(value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const COLORS = ['#38bdf8','#8b5cf6','#22c55e','#f59e0b','#ef4444','#14b8a6','#60a5fa','#d946ef','#eab308','#10b981'];

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

function deriveClusters(ids, edges, root) {
  const nonRootAdj = new Map(ids.filter(id => id !== root).map(id => [id, new Set()]));
  edges.forEach(edge => {
    if (edge.from === root || edge.to === root) return;
    nonRootAdj.get(edge.from)?.add(edge.to);
    nonRootAdj.get(edge.to)?.add(edge.from);
  });

  const assigned = new Map();
  let cluster = 0;
  const visited = new Set();
  for (const id of nonRootAdj.keys()) {
    if (visited.has(id)) continue;
    const component = [];
    const queue = [id];
    visited.add(id);
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i]; component.push(current);
      for (const next of nonRootAdj.get(current) || []) {
        if (!visited.has(next)) { visited.add(next); queue.push(next); }
      }
    }
    if (component.length >= 2) {
      component.forEach(member => assigned.set(member, cluster));
      cluster += 1;
    }
  }

  const signatures = new Map();
  ids.filter(id => id !== root && !assigned.has(id)).forEach(id => {
    let incoming = 0, outgoing = 0;
    const assets = new Map();
    edges.forEach(edge => {
      if (edge.from === root && edge.to === id) incoming += 1;
      if (edge.from === id && edge.to === root) outgoing += 1;
      if (edge.from === id || edge.to === id) assets.set(edge.asset, (assets.get(edge.asset) || 0) + 1);
    });
    const dominantAsset = [...assets.entries()].sort((a,b) => b[1]-a[1])[0]?.[0] || 'OTHER';
    const direction = incoming && outgoing ? 'BOTH' : incoming ? 'FROM_ROOT' : outgoing ? 'TO_ROOT' : 'OTHER';
    const signature = `${direction}:${dominantAsset}`;
    if (!signatures.has(signature)) signatures.set(signature, cluster++);
    assigned.set(id, signatures.get(signature));
  });
  if (root) assigned.set(root, -1);
  return { assigned, count: cluster };
}

function buildGraph(transactions, rootAddress, nodeContext) {
  const root = normalized(rootAddress);
  const edges = transactions.filter(tx => tx.from_address && tx.to_address && tx.hash).map((tx, index) => ({
    id: `${tx.hash}-${tx.category || tx.asset || 'tx'}-${index}`,
    from: normalized(tx.from_address), to: normalized(tx.to_address), tx,
    value: numeric(tx.value), asset: assetName(tx), risk: Number(tx.risk_score || 0), time: timestamp(tx),
  }));
  const ids = [...new Set(edges.flatMap(edge => [edge.from, edge.to]))];
  if (root && !ids.includes(root)) ids.unshift(root);
  const { assigned: clusterMap, count: clusterCount } = deriveClusters(ids, edges, root);

  const nodes = ids.map(id => {
    const seed = hash(id), angle = ((seed % 10000) / 10000) * Math.PI * 2;
    const radius = id === root ? 0 : 70 + (seed % 150);
    return {
      id,
      x: id === root ? 0 : Math.cos(angle) * radius,
      y: id === root ? 0 : Math.sin(angle) * radius * .78,
      z: id === root ? 0 : (((seed >>> 8) % 120) - 60),
      vx: 0, vy: 0, vz: 0,
      cluster: clusterMap.get(id) ?? 0,
    };
  });
  const nodeMap = new Map(nodes.map(node => [node.id, node]));
  const linkedEdges = edges.map(edge => ({ ...edge, source: nodeMap.get(edge.from), target: nodeMap.get(edge.to) }));

  const pairWeights = new Map();
  linkedEdges.forEach(edge => {
    const key = [edge.from, edge.to].sort().join('|');
    pairWeights.set(key, (pairWeights.get(key) || 0) + 1);
  });

  const iterations = Math.min(180, 70 + nodes.length);
  for (let tick = 0; tick < iterations; tick += 1) {
    const cooling = 1 - tick / iterations;
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        let dx = a.x-b.x, dy = a.y-b.y, dz = a.z-b.z;
        let distance2 = dx*dx + dy*dy + dz*dz;
        if (!Number.isFinite(distance2) || distance2 < 36) {
          const nudge = ((hash(`${a.id}:${b.id}`) % 1000) / 1000 - .5) || .1;
          dx = 10+nudge*4; dy = 8-nudge*3; dz = 6+nudge*2; distance2 = dx*dx+dy*dy+dz*dz;
        }
        const distance = Math.sqrt(distance2), repulsion = (a.cluster === b.cluster ? 1450 : 2300) / Math.max(225,distance2);
        dx/=distance; dy/=distance; dz/=distance;
        a.vx+=dx*repulsion; a.vy+=dy*repulsion; a.vz+=dz*repulsion;
        b.vx-=dx*repulsion; b.vy-=dy*repulsion; b.vz-=dz*repulsion;
      }
    }
    linkedEdges.forEach(edge => {
      const a=edge.source,b=edge.target; if(!a||!b)return;
      let dx=b.x-a.x,dy=b.y-a.y,dz=b.z-a.z;
      const distance=Math.max(1,Math.sqrt(dx*dx+dy*dy+dz*dz));
      const weight=pairWeights.get([edge.from,edge.to].sort().join('|'))||1;
      const desired=a.cluster===b.cluster?64:96;
      const force=(distance-desired)*.0015*Math.min(2.2,1+weight*.12);
      dx/=distance;dy/=distance;dz/=distance;
      a.vx+=dx*force;a.vy+=dy*force;a.vz+=dz*force;
      b.vx-=dx*force;b.vy-=dy*force;b.vz-=dz*force;
    });
    nodes.forEach(node => {
      const centerStrength=node.id===root?.06:.0012;
      node.vx+=-node.x*centerStrength;node.vy+=-node.y*centerStrength;node.vz+=-node.z*centerStrength;
      node.vx*=.82;node.vy*=.82;node.vz*=.82;
      node.x+=node.vx*cooling*14;node.y+=node.vy*cooling*14;node.z+=node.vz*cooling*10;
    });
  }

  // Hard safety boundary: sanitize, re-center on root, and normalize every final position.
  nodes.forEach(node => {
    if (![node.x,node.y,node.z].every(Number.isFinite)) {
      const seed=hash(node.id),angle=(seed%10000)/10000*Math.PI*2;
      node.x=Math.cos(angle)*140;node.y=Math.sin(angle)*105;node.z=((seed>>>8)%100)-50;
    }
  });
  const rootNode=nodeMap.get(root);
  const ox=rootNode?.x||0,oy=rootNode?.y||0,oz=rootNode?.z||0;
  nodes.forEach(node=>{node.x-=ox;node.y-=oy;node.z-=oz;});
  const maxRadius=Math.max(1,...nodes.map(node=>Math.sqrt(node.x*node.x+node.y*node.y+node.z*node.z)));
  const normalization=260/maxRadius;
  nodes.forEach(node=>{node.x*=normalization;node.y*=normalization;node.z*=normalization;});
  if(rootNode){rootNode.x=0;rootNode.y=0;rootNode.z=0;}

  const metrics=new Map(nodes.map(node=>[node.id,{incoming:0,outgoing:0,transfers:0,peers:new Set(),assets:new Set(),volume:0,maxRisk:Number(nodeContext[node.id]?.maxRisk||0)}]));
  linkedEdges.forEach(edge=>{
    const from=metrics.get(edge.from),to=metrics.get(edge.to);
    if(from){from.outgoing++;from.transfers++;from.peers.add(edge.to);from.assets.add(edge.asset);from.volume+=edge.value;from.maxRisk=Math.max(from.maxRisk,edge.risk);}
    if(to){to.incoming++;to.transfers++;to.peers.add(edge.from);to.assets.add(edge.asset);to.volume+=edge.value;to.maxRisk=Math.max(to.maxRisk,edge.risk);}
  });
  return {root,nodes,edges:linkedEdges,nodeMap,metrics,clusterCount};
}

function rotate(node,camera){const cy=Math.cos(camera.yaw),sy=Math.sin(camera.yaw),cp=Math.cos(camera.pitch),sp=Math.sin(camera.pitch),x1=node.x*cy+node.z*sy,z1=-node.x*sy+node.z*cy;return{x:x1,y:node.y*cp-z1*sp,z:node.y*sp+z1*cp};}
function project(node,camera,width,height){const p=rotate(node,camera),depth=Math.max(360,900-p.z),perspective=900/depth;return{x:width/2+p.x*perspective*camera.zoom,y:height/2+p.y*perspective*camera.zoom,z:p.z,perspective};}
function segmentDistance(px,py,ax,ay,bx,by){const dx=bx-ax,dy=by-ay,l2=dx*dx+dy*dy;if(!l2)return Math.hypot(px-ax,py-ay);const t=clamp(((px-ax)*dx+(py-ay)*dy)/l2,0,1);return Math.hypot(px-(ax+t*dx),py-(ay+t*dy));}
function bubbleColor(node,metric,context,selected,hovered,root,expanded){if(node.id===root)return'#31d7f5';if(selected)return'#ffd166';if(hovered)return'#f8fafc';if(expanded.has(node.id))return'#f59e0b';if((context.entityLabels||[]).length)return'#34d399';if(Number(metric?.maxRisk||0)>=70)return'#fb7185';return COLORS[Math.abs(node.cluster)%COLORS.length];}

export default function BubbleInvestigationGraph({transactions=[],rootAddress='',onExpandAddress,expandingAddress='',expandedAddresses=[],nodeContext={}}){
  const canvasRef=useRef(null),hitRef=useRef({nodes:[],edges:[]}),dragRef=useRef(null),animationRef=useRef(null),cameraRef=useRef({yaw:.15,pitch:-.07,zoom:1});
  const [selectedNode,setSelectedNode]=useState(''),[selectedEdge,setSelectedEdge]=useState(''),[hoveredNode,setHoveredNode]=useState(''),[asset,setAsset]=useState('ALL'),[timeWindow,setTimeWindow]=useState('ALL'),[minRisk,setMinRisk]=useState(0),[query,setQuery]=useState(''),[isolate,setIsolate]=useState(false),[balanceCache,setBalanceCache]=useState({}),[balanceLoading,setBalanceLoading]=useState(false),[balanceRefresh,setBalanceRefresh]=useState(0);

  const expanded=useMemo(()=>new Set(expandedAddresses.map(normalized)),[expandedAddresses]);
  const graph=useMemo(()=>buildGraph(transactions,rootAddress,nodeContext),[transactions,rootAddress,nodeContext]);
  const assets=useMemo(()=>['ALL',...[...new Set(graph.edges.map(edge=>edge.asset))].sort()],[graph]);
  const newest=useMemo(()=>Math.max(0,...graph.edges.map(edge=>edge.time||0)),[graph]);
  const filteredEdges=useMemo(()=>{const windows={'24H':86400000,'7D':604800000,'30D':2592000000},cutoff=timeWindow==='ALL'||!newest?0:newest-windows[timeWindow];return graph.edges.filter(edge=>(asset==='ALL'||edge.asset===asset)&&edge.risk>=Number(minRisk||0)&&(!cutoff||!edge.time||edge.time>=cutoff)&&(!isolate||!selectedNode||edge.from===selectedNode||edge.to===selectedNode));},[graph,asset,minRisk,timeWindow,newest,isolate,selectedNode]);
  const visibleIds=useMemo(()=>new Set(filteredEdges.flatMap(edge=>[edge.from,edge.to]).concat(graph.root?[graph.root]:[])),[filteredEdges,graph.root]);
  const visibleNodes=useMemo(()=>graph.nodes.filter(node=>visibleIds.has(node.id)),[graph,visibleIds]);
  const selectedMetric=selectedNode?graph.metrics.get(selectedNode):null,selectedContext=selectedNode?nodeContext[selectedNode]||{}:{},selectedBalance=selectedNode?balanceCache[selectedNode]:null,selectedEdgeRecord=selectedEdge?graph.edges.find(edge=>edge.id===selectedEdge):null;

  useEffect(()=>{
    const canvas=canvasRef.current;if(!canvas||!visibleNodes.length)return;
    const width=canvas.clientWidth||900,height=canvas.clientHeight||650;
    // Positions are normalized to a 260-unit sphere, so this fit is deterministic.
    cameraRef.current.zoom=clamp(Math.min(width,height)*.78/520,.75,2.4);
    cameraRef.current.yaw=.15;cameraRef.current.pitch=-.07;
  },[graph,visibleNodes.length,asset,timeWindow,isolate]);

  useEffect(()=>{
    if(!selectedNode)return;const cached=balanceCache[selectedNode];if(cached?.status==='ready'&&Date.now()-cached.fetchedAt<30000&&!balanceRefresh)return;
    let cancelled=false;setBalanceLoading(true);
    api.getWalletBalance(selectedNode).then(data=>{if(!cancelled)setBalanceCache(previous=>({...previous,[selectedNode]:{status:'ready',...data,fetchedAt:Date.now()}}));}).catch(error=>{if(!cancelled)setBalanceCache(previous=>({...previous,[selectedNode]:{status:'error',message:error.message||'Live balance unavailable',fetchedAt:Date.now()}}));}).finally(()=>{if(!cancelled){setBalanceLoading(false);setBalanceRefresh(0);}});
    return()=>{cancelled=true;};
  },[selectedNode,balanceCache,balanceRefresh]);

  useEffect(()=>{
    const canvas=canvasRef.current;if(!canvas)return undefined;const ctx=canvas.getContext('2d',{alpha:false});if(!ctx)return undefined;const dpr=Math.min(window.devicePixelRatio||1,2);let stopped=false;
    const draw=time=>{
      if(stopped)return;const rect=canvas.getBoundingClientRect(),width=Math.max(1,rect.width),height=Math.max(1,rect.height);if(canvas.width!==Math.floor(width*dpr)||canvas.height!==Math.floor(height*dpr)){canvas.width=Math.floor(width*dpr);canvas.height=Math.floor(height*dpr);}ctx.setTransform(dpr,0,0,dpr,0,0);
      const bg=ctx.createRadialGradient(width*.5,height*.46,20,width*.5,height*.46,Math.max(width,height)*.75);bg.addColorStop(0,'#10233b');bg.addColorStop(.43,'#07111f');bg.addColorStop(1,'#02060b');ctx.fillStyle=bg;ctx.fillRect(0,0,width,height);
      ctx.fillStyle='rgba(125,211,252,.045)';for(let x=24;x<width;x+=50)for(let y=28;y<height;y+=50)ctx.fillRect(x,y,1,1);
      const projected=new Map();visibleNodes.forEach(node=>projected.set(node.id,project(node,cameraRef.current,width,height)));
      const edgeHits=[];filteredEdges.forEach(edge=>{const a=projected.get(edge.from),b=projected.get(edge.to);if(!a||!b)return;const related=selectedNode&&(edge.from===selectedNode||edge.to===selectedNode),active=edge.id===selectedEdge,token=edge.tx.category==='erc20';ctx.save();ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=active?'rgba(253,224,71,.95)':token?'rgba(196,181,253,.22)':'rgba(125,211,252,.16)';ctx.globalAlpha=selectedNode&&!related?.08:related?.78:.55;ctx.lineWidth=active?2.7:related?1.5:.7;if(token)ctx.setLineDash([5,5]);ctx.stroke();ctx.restore();edgeHits.push({id:edge.id,ax:a.x,ay:a.y,bx:b.x,by:b.y});if(active||related||hoveredNode===edge.from||hoveredNode===edge.to){const t=(time*.00016+(hash(edge.id)%1000)/1000)%1,px=a.x+(b.x-a.x)*t,py=a.y+(b.y-a.y)*t;ctx.beginPath();ctx.arc(px,py,active?3.2:2.1,0,Math.PI*2);ctx.fillStyle=active?'#fde68a':token?'#c4b5fd':'#7dd3fc';ctx.fill();}});
      const nodeHits=[];[...visibleNodes].sort((a,b)=>(projected.get(a.id)?.z||0)-(projected.get(b.id)?.z||0)).forEach(node=>{const point=projected.get(node.id),metric=graph.metrics.get(node.id),context=nodeContext[node.id]||{};if(!point)return;const selected=node.id===selectedNode,hovered=node.id===hoveredNode,connected=selectedNode&&filteredEdges.some(edge=>(edge.from===selectedNode&&edge.to===node.id)||(edge.to===selectedNode&&edge.from===node.id)),dimmed=selectedNode&&!selected&&!connected,activity=Math.log2(2+(metric?.transfers||0)+(metric?.peers?.size||0));const live=balanceCache[node.id]?.status==='ready'?Number(balanceCache[node.id].balance_eth??balanceCache[node.id].eth??0):0,balanceBoost=live>0?Math.min(10,Math.log10(1+live)*4.2):0,base=node.id===graph.root?24:9+activity*3.6+balanceBoost,radius=clamp(base*clamp(point.perspective,.75,1.45)*(selected?1.13:hovered?1.07:1),8,node.id===graph.root?44:34),color=bubbleColor(node,metric,context,selected,hovered,graph.root,expanded);ctx.save();ctx.globalAlpha=dimmed?.14:1;const glow=ctx.createRadialGradient(point.x,point.y,0,point.x,point.y,radius*2.05);glow.addColorStop(0,`${color}58`);glow.addColorStop(.48,`${color}1f`);glow.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow;ctx.beginPath();ctx.arc(point.x,point.y,radius*2.05,0,Math.PI*2);ctx.fill();const sphere=ctx.createRadialGradient(point.x-radius*.34,point.y-radius*.38,radius*.06,point.x,point.y,radius);sphere.addColorStop(0,'#fff');sphere.addColorStop(.1,color);sphere.addColorStop(.58,`${color}d8`);sphere.addColorStop(1,'#06101b');ctx.fillStyle=sphere;ctx.beginPath();ctx.arc(point.x,point.y,radius,0,Math.PI*2);ctx.fill();ctx.strokeStyle=selected?'#fff4b8':node.id===graph.root?'#a5f3fc':`${color}d0`;ctx.lineWidth=selected?3:node.id===graph.root?2.8:1.3;ctx.stroke();if(selected||hovered||node.id===graph.root){ctx.font=selected||node.id===graph.root?'600 12px ui-monospace, SFMono-Regular, Menlo, monospace':'11px ui-monospace, SFMono-Regular, Menlo, monospace';ctx.fillStyle='rgba(241,245,249,.94)';ctx.textBaseline='middle';ctx.fillText(node.id===graph.root?`ROOT ${short(node.id)}`:short(node.id),point.x+radius+8,point.y);}ctx.restore();nodeHits.push({id:node.id,x:point.x,y:point.y,r:radius+7});});hitRef.current={nodes:nodeHits,edges:edgeHits};animationRef.current=requestAnimationFrame(draw);
    };animationRef.current=requestAnimationFrame(draw);return()=>{stopped=true;cancelAnimationFrame(animationRef.current);};
  },[filteredEdges,visibleNodes,selectedNode,selectedEdge,hoveredNode,graph,nodeContext,expanded,balanceCache]);

  const pointer=event=>{const rect=canvasRef.current.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top};};
  const hitAt=event=>{const p=pointer(event),node=[...hitRef.current.nodes].reverse().find(item=>Math.hypot(p.x-item.x,p.y-item.y)<=item.r);if(node)return{kind:'node',id:node.id};const edge=[...hitRef.current.edges].reverse().find(item=>segmentDistance(p.x,p.y,item.ax,item.ay,item.bx,item.by)<=7);return edge?{kind:'edge',id:edge.id}:null;};
  const onPointerDown=event=>{const hit=hitAt(event);if(hit?.kind==='node'){setSelectedNode(hit.id);setSelectedEdge('');return;}if(hit?.kind==='edge'){setSelectedEdge(hit.id);setSelectedNode('');return;}dragRef.current={x:event.clientX,y:event.clientY,yaw:cameraRef.current.yaw,pitch:cameraRef.current.pitch};event.currentTarget.setPointerCapture?.(event.pointerId);};
  const onPointerMove=event=>{if(dragRef.current){const dx=event.clientX-dragRef.current.x,dy=event.clientY-dragRef.current.y;cameraRef.current.yaw=dragRef.current.yaw+dx*.007;cameraRef.current.pitch=clamp(dragRef.current.pitch+dy*.005,-.95,.95);return;}const hit=hitAt(event);setHoveredNode(hit?.kind==='node'?hit.id:'');};
  const onWheel=event=>{event.preventDefault();cameraRef.current.zoom=clamp(cameraRef.current.zoom*(event.deltaY>0?.9:1.1),.55,3);};
  const search=()=>{const q=query.trim().toLowerCase();if(!q)return;const node=graph.nodes.find(item=>item.id.includes(q)||(nodeContext[item.id]?.entityLabels||[]).some(label=>String(label.entity_name||label.entity_id||'').toLowerCase().includes(q)));if(node){setSelectedNode(node.id);setSelectedEdge('');}};
  const resetView=()=>{setSelectedNode('');setSelectedEdge('');setHoveredNode('');setIsolate(false);cameraRef.current.yaw=.15;cameraRef.current.pitch=-.07;const canvas=canvasRef.current;if(canvas)cameraRef.current.zoom=clamp(Math.min(canvas.clientWidth||900,canvas.clientHeight||650)*.78/520,.75,2.4);};
  const copyAddress=()=>{if(selectedNode&&navigator.clipboard)navigator.clipboard.writeText(selectedNode).catch(()=>{});};

  return <section className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#050a12] shadow-2xl">
    <div className="border-b border-white/[0.06] bg-[#080e18]/90 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[.2em] text-cyan-300">Bubble investigation map</p><h2 className="mt-2 text-xl font-semibold text-white">Live wallet bubble network</h2><p className="mt-2 max-w-3xl text-sm text-slate-400">Normalized 3D layout, meaningful relationship groups, live ETH balance on selection, and evidence-backed expansion.</p></div><div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full border border-cyan-400/20 bg-cyan-400/[.06] px-3 py-1 text-cyan-200">{visibleNodes.length} bubbles</span><span className="rounded-full border border-violet-400/20 bg-violet-400/[.06] px-3 py-1 text-violet-200">{filteredEdges.length} links</span><span className="rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1 text-slate-400">{graph.clusterCount} groups</span></div></div>
      <div className="mt-4 grid gap-2 lg:grid-cols-[minmax(240px,1fr)_150px_150px_170px_auto]"><div className="flex gap-2"><input value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Enter')search();}} aria-label="Find wallet or entity" placeholder="Find wallet or entity…" className="soft-input min-w-0 flex-1"/><button type="button" onClick={search} className="secondary-button">Focus</button></div><select value={asset} onChange={event=>setAsset(event.target.value)} className="soft-input" aria-label="Asset filter">{assets.map(item=><option key={item} value={item}>{item==='ALL'?'All assets':item}</option>)}</select><select value={timeWindow} onChange={event=>setTimeWindow(event.target.value)} className="soft-input" aria-label="Time window"><option value="ALL">All time</option><option value="24H">24 hours</option><option value="7D">7 days</option><option value="30D">30 days</option></select><label className="rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-xs text-slate-400">Risk ≥ {minRisk}<input type="range" min="0" max="100" value={minRisk} onChange={event=>setMinRisk(Number(event.target.value))} className="mt-1 w-full" aria-label="Minimum risk"/></label><button type="button" onClick={resetView} className="secondary-button">Fit map</button></div>
    </div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="relative min-h-[580px] overflow-hidden"><canvas ref={canvasRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={()=>{dragRef.current=null;}} onPointerCancel={()=>{dragRef.current=null;}} onPointerLeave={()=>{if(!dragRef.current)setHoveredNode('');}} onWheel={onWheel} className="h-[580px] w-full touch-none cursor-grab outline-none active:cursor-grabbing lg:h-[700px]" tabIndex={0} aria-label="Interactive 3D bubble map. Drag to orbit, wheel to zoom, click a bubble for live ETH balance."/><div className="pointer-events-none absolute left-4 top-4 rounded-full border border-cyan-400/15 bg-[#04101d]/85 px-3 py-1.5 text-[10px] uppercase tracking-[.17em] text-cyan-200">Drag orbit · wheel zoom · click bubble</div><div className="pointer-events-none absolute bottom-4 left-4 flex flex-wrap gap-2 text-[10px] text-slate-500"><span className="text-cyan-300">● root</span><span className="text-emerald-300">● labeled</span><span className="text-rose-300">● high risk</span><span>faint lines = loaded relationship</span></div></div>
      <aside className="space-y-4 border-t border-white/[0.06] bg-[#080e18] p-5 lg:border-l lg:border-t-0">
        <div className="flex items-center justify-between"><h3 className="text-lg font-semibold text-white">Wallet details</h3>{selectedNode&&<button type="button" onClick={()=>setIsolate(value=>!value)} className="text-xs text-cyan-300 underline">{isolate?'Show all':'Isolate'}</button>}</div>
        {selectedNode?<><div className="rounded-2xl border border-cyan-400/15 bg-gradient-to-br from-cyan-400/[.07] to-transparent p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-[10px] uppercase tracking-[.16em] text-slate-500">Selected wallet</p><p className="mt-1 break-all font-mono text-sm text-cyan-300">{selectedNode}</p></div><button type="button" onClick={copyAddress} className="rounded-md border border-slate-700 px-2 py-1 text-[10px] text-slate-400">Copy</button></div><div className="mt-4 border-t border-white/[0.06] pt-4"><div className="flex items-center justify-between"><p className="text-[10px] uppercase tracking-[.16em] text-slate-500">Live ETH balance</p>{selectedBalance?.status==='ready'&&<span className="text-[10px] text-emerald-300">mainnet · live</span>}</div>{balanceLoading&&!selectedBalance&&<div className="mt-3 h-9 animate-pulse rounded-lg bg-slate-800/70"/>}{selectedBalance?.status==='ready'&&<><p className="mt-2 text-3xl font-semibold tracking-tight text-white">{Number(selectedBalance.balance_eth??selectedBalance.eth??0).toLocaleString(undefined,{maximumFractionDigits:8})} <span className="text-lg text-slate-400">ETH</span></p><p className="mt-1 text-[11px] text-slate-500">Block {selectedBalance.block_number?Number(selectedBalance.block_number).toLocaleString('en-US'):'latest provider block'}</p><button type="button" onClick={()=>setBalanceRefresh(value=>value+1)} className="mt-2 text-[11px] text-cyan-300 underline">Refresh live balance</button></>}{selectedBalance?.status==='error'&&<><p className="mt-2 text-sm text-rose-300">{selectedBalance.message||'Live balance unavailable'}</p><button type="button" onClick={()=>setBalanceRefresh(value=>value+1)} className="mt-2 text-[11px] text-cyan-300 underline">Retry</button></>}</div></div><div className="grid grid-cols-2 gap-2"><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Transfers</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.transfers||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Peers</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.peers?.size||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Incoming</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.incoming||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-xs text-slate-500">Outgoing</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.outgoing||0}</p></div><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 col-span-2"><p className="text-xs text-slate-500">Max risk</p><p className="mt-1 text-2xl font-semibold text-white">{selectedMetric?.maxRisk||0}</p></div></div>{(selectedContext.entityLabels||[]).map((label,index)=><div key={`${label.source}-${index}`} className="rounded-xl border border-emerald-400/15 bg-emerald-400/[.04] p-3"><p className="font-medium text-emerald-200">{label.entity_name||label.entity_id}</p><p className="mt-1 text-xs text-slate-500">Source: {label.source}</p></div>)}{selectedMetric?.assets?.size>0&&<p className="text-xs text-slate-400">Observed assets: {[...selectedMetric.assets].slice(0,8).join(', ')}</p>}{onExpandAddress&&selectedNode!==graph.root&&!expanded.has(selectedNode)&&<button type="button" onClick={()=>onExpandAddress(selectedNode)} disabled={Boolean(expandingAddress)} className="primary-button w-full disabled:opacity-50">{normalized(expandingAddress)===selectedNode?'Expanding…':'Expand one observed hop'}</button>}<div className={selectedNode===graph.root?'grid grid-cols-1 gap-2':'grid grid-cols-2 gap-2'}><a href={`https://etherscan.io/address/${selectedNode}`} target="_blank" rel="noreferrer" className="secondary-button text-center">Etherscan ↗</a>{selectedNode!==graph.root&&<button type="button" onClick={()=>{setSelectedNode(graph.root);setSelectedEdge('');}} className="secondary-button">Back to root</button>}</div></>:selectedEdgeRecord?<><p className="text-xs uppercase tracking-[.16em] text-slate-500">Selected transfer</p><p className="break-all font-mono text-xs text-slate-300">{selectedEdgeRecord.from}</p><p className="text-cyan-300">↓</p><p className="break-all font-mono text-xs text-slate-300">{selectedEdgeRecord.to}</p><div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-300"><p>Asset: <span className="text-white">{selectedEdgeRecord.asset}</span></p><p className="mt-1">Value: <span className="text-white">{selectedEdgeRecord.tx.value??'—'}</span></p><p className="mt-1">Risk: <span className="text-white">{selectedEdgeRecord.risk}</span></p></div><a href={selectedEdgeRecord.tx.evidence_url||`https://etherscan.io/tx/${selectedEdgeRecord.tx.hash}`} target="_blank" rel="noreferrer" className="text-sm text-cyan-300 underline">Verify transaction ↗</a></>:<div className="rounded-2xl border border-slate-800 bg-slate-950/45 p-4 text-sm leading-6 text-slate-400">All loaded bubbles are normalized into the visible 3D scene. Click any bubble to fetch its live ETH balance and inspect its evidence.</div>}
        <div className="border-t border-white/[0.06] pt-4 text-xs leading-5 text-slate-600">Bubble size uses observed activity and, after a live balance is fetched, a logarithmic ETH-balance boost. Groups are based on non-root connectivity plus root direction/asset behavior—not ownership attribution.</div>
      </aside>
    </div>
  </section>;
}
