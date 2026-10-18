import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';

const norm = value => String(value || '').toLowerCase();
const short = value => value ? value.slice(0,8)+'…'+value.slice(-5) : '—';
const palette = [[.22,.78,.98],[.63,.48,.98],[.18,.81,.62],[.99,.65,.23],[.95,.4,.51],[.2,.82,.74]];
const clamp = (n,a,b) => Math.max(a,Math.min(b,n));
function shader(gl,type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
function program(gl,vertex,fragment){const p=gl.createProgram();gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,vertex));gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,fragment));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return p;}
function createRenderer(gl){
  const points=program(gl,'attribute vec2 xy;attribute float size;attribute vec3 color;varying vec3 c;void main(){gl_Position=vec4(xy,0.,1.);gl_PointSize=size;c=color;}','precision mediump float;varying vec3 c;void main(){vec2 uv=gl_PointCoord*2.-1.;float d=length(uv);if(d>1.)discard;float highlight=pow(max(0.,1.-length(uv-vec2(-.32,-.38))*1.05),2.);float rim=smoothstep(.60,.91,d)*(1.-smoothstep(.93,1.,d));float inner=1.-smoothstep(.1,.95,d);vec3 sphere=c*(.38+inner*.5)+vec3(1.)*highlight*.66+c*rim*.9;gl_FragColor=vec4(sphere,1.-smoothstep(.94,1.,d));}');
  const lines=program(gl,'attribute vec2 xy;attribute vec4 color;varying vec4 c;void main(){gl_Position=vec4(xy,0.,1.);c=color;}','precision mediump float;varying vec4 c;void main(){gl_FragColor=c;}');
  return {points,lines,buffer:gl.createBuffer()};
}
const headerClass='rounded-xl border border-slate-700 bg-[#0b1525] px-3 py-2 text-xs text-slate-200';
export default function ScalableBubbleInvestigationGraph({transactions=[],rootAddress='',nodeContext={},expandedAddresses=[],onExpandAddress,expandingAddress=''}) {
 const canvasRef=useRef(null),sceneRef=useRef(null),camera=useRef({yaw:.1,pitch:-.12,zoom:1}),pointer=useRef(null),projected=useRef([]),labelRefs=useRef(new Map()),zoomTarget=useRef(null);
 const [motion,setMotion]=useState(()=>typeof window!=='undefined'?!window.matchMedia('(prefers-reduced-motion: reduce)').matches:false);
 const [layout,setLayout]=useState(null),[selected,setSelected]=useState(''),[search,setSearch]=useState(''),[asset,setAsset]=useState('ALL'),[error,setError]=useState(''),[balance,setBalance]=useState(null),[loading,setLoading]=useState(false),[isolate,setIsolate]=useState(false);
 const root=norm(rootAddress);
 const edges=useMemo(()=>transactions.filter(tx=>tx.from_address&&tx.to_address&&tx.hash).map((tx,i)=>({id:tx.hash+'-'+i,from:norm(tx.from_address),to:norm(tx.to_address),asset:String(tx.asset||'ETH').toUpperCase(),tx})),[transactions]);
 const addresses=useMemo(()=>[...new Set([...edges.flatMap(e=>[e.from,e.to]),...(root?[root]:[])])],[edges,root]);
 const assets=useMemo(()=>['ALL',...[...new Set(edges.map(e=>e.asset))].sort()],[edges]);
 const scoped=useMemo(()=>edges.filter(e=>(asset==='ALL'||e.asset===asset)&&(!isolate||!selected||e.from===selected||e.to===selected)),[edges,asset,isolate,selected]);
 const visibleSet=useMemo(()=>new Set([...scoped.flatMap(e=>[e.from,e.to]),root]),[scoped,root]);
 const importantLabels=useMemo(()=>{const counts=new Map();for(const edge of edges){counts.set(edge.from,(counts.get(edge.from)||0)+1);counts.set(edge.to,(counts.get(edge.to)||0)+1);}return [...new Set([root,selected,...[...counts].sort((a,b)=>b[1]-a[1]).slice(0,6).map(x=>x[0])])].filter(Boolean).slice(0,8);},[edges,root,selected]);
 const addressesKey=addresses.join(',');
 const edgeKey=edges.map(e=>e.from+e.to).join(',');
 useEffect(()=>{
   if(!addresses.length){setLayout(null);return;}
   const worker=new Worker(new URL('../workers/graphLayout.worker.js',import.meta.url),{type:'module'});
   let alive=true;
   worker.onmessage=event=>{if(!alive)return;if(event.data.error){setError('Graph layout unavailable: '+event.data.error);return;}setLayout(event.data);};
   worker.onerror=()=>{if(alive)setError('Graph layout worker failed.');};
   worker.postMessage({seq:1,payload:{addresses,links:edges.map(e=>[e.from,e.to]),root}});
   return()=>{alive=false;worker.terminate();};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[addressesKey,edgeKey,root]);
 useEffect(()=>{
   if(!selected){setBalance(null);return;}
   let active=true;setLoading(true);setBalance(null);
   api.getWalletBalance(selected).then(data=>{if(active)setBalance(data);}).catch(()=>{if(active)setBalance({unavailable:true});}).finally(()=>{if(active)setLoading(false);});
   return()=>{active=false;};
 },[selected]);
 useEffect(()=>{
   const canvas=canvasRef.current;
   if(!canvas||!layout)return;
   const w=canvas.clientWidth||800,h=canvas.clientHeight||650;
   camera.current.zoom=clamp(Math.min(w*.42/layout.bounds.x,h*.42/layout.bounds.y),.12,3);
   zoomTarget.current=camera.current.zoom;
 },[layout]);
 useEffect(()=>{
   const canvas=canvasRef.current;if(!canvas||!layout)return undefined;
   const gl=canvas.getContext('webgl',{alpha:true,antialias:true});
   if(!gl){setError('WebGL unavailable in this browser');return undefined;}
   let renderer;try{renderer=createRenderer(gl);}catch(e){setError('WebGL shader failed: '+e.message);return undefined;}
   gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
   const dpr=Math.min(devicePixelRatio||1,2);
   const index=new Map(addresses.map((a,i)=>[a,i]));
   let stopped=false,raf;
   const draw=()=>{
     if(stopped)return;
     const w=canvas.clientWidth||1,h=canvas.clientHeight||1;
     const pw=Math.floor(w*dpr),ph=Math.floor(h*dpr);
     if(canvas.width!==pw||canvas.height!==ph){canvas.width=pw;canvas.height=ph;}
     gl.viewport(0,0,pw,ph);gl.clearColor(.014,.031,.058,0);gl.clear(gl.COLOR_BUFFER_BIT);
     const cam=camera.current;
     if(zoomTarget.current!==null)cam.zoom+=(zoomTarget.current-cam.zoom)*.16;
     const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
     const pts=addresses.map((id,i)=>{
       const x=layout.positions[i*3],y=layout.positions[i*3+1],z=layout.positions[i*3+2],rx=x*cy+z*sy,rz=-x*sy+z*cy,ry=y*cp-rz*sp,pz=y*sp+rz*cp,scale=950/Math.max(400,950-pz);
       return {id,x:w/2+rx*scale*cam.zoom,y:h/2+ry*scale*cam.zoom,scale};
     });projected.current=pts;
     for(const [id,element] of labelRefs.current){const point=pts[index.get(id)];const show=point&&visibleSet.has(id);element.style.display=show?'block':'none';if(show)element.style.transform=`translate3d(${point.x}px,${point.y}px,0) translate(-50%,-155%)`;}
     const lines=[];
     const particles=[];
     const tick=performance.now()*0.00016;
     for(const edge of scoped.slice(0,12000)){
       const a=pts[index.get(edge.from)],b=pts[index.get(edge.to)];
       if(!a||!b)continue;
       const active=selected&&(edge.from===selected||edge.to===selected),opacity=selected?(active?.82:.075):.29;
       const col=edge.asset==='ETH'?[.32,.76,.96]:[.69,.48,.99];
       lines.push(a.x/w*2-1,1-a.y/h*2,...col,opacity,b.x/w*2-1,1-b.y/h*2,...col,opacity);
       if(motion&&particles.length<350*6&&(!selected||active)){
         // Particle position travels FROM sender TO recipient. It is an animated
         // direction indicator for recorded edges, not a live transaction event.
         const seed=(index.get(edge.from)*31+index.get(edge.to)*17)%101;
         const t=(tick+seed/101)%1;
         particles.push((a.x+(b.x-a.x)*t)/w*2-1,1-(a.y+(b.y-a.y)*t)/h*2,clamp(4*dpr,2,7),...col);
       }
     }
     const buf=renderer.buffer;
     if(lines.length){gl.useProgram(renderer.lines);gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(lines),gl.DYNAMIC_DRAW);const p=gl.getAttribLocation(renderer.lines,'xy'),c=gl.getAttribLocation(renderer.lines,'color');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(c);gl.vertexAttribPointer(c,4,gl.FLOAT,false,24,8);gl.drawArrays(gl.LINES,0,lines.length/6);}
     const values=particles;
     for(let i=0;i<pts.length;i++){
       const p=pts[i],id=p.id;
       if(asset!=='ALL'&&!visibleSet.has(id))continue;
       if(isolate&&selected&&!visibleSet.has(id))continue;
       const color=id===selected?[1,.8,.25]:id===root?[.2,.85,1]:nodeContext[id]?.entityLabels?.length?[.2,.86,.6]:palette[i%palette.length];
       const activity=layout.degree[i]||0;
       const liveEth=id===selected&&balance&&!balance.unavailable?Number(balance.balance_eth??balance.eth??0):0;
       const size=clamp((17+Math.log2(activity+1)*5+(id===root?16:0)+(id===selected?10:0)+(liveEth>0?Math.min(10,Math.log10(1+liveEth)*4):0))*p.scale*cam.zoom,8,72)*dpr;
       values.push(p.x/w*2-1,1-p.y/h*2,size,...color);
     }
     if(values.length){gl.useProgram(renderer.points);gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(values),gl.DYNAMIC_DRAW);const p=gl.getAttribLocation(renderer.points,'xy'),s=gl.getAttribLocation(renderer.points,'size'),c=gl.getAttribLocation(renderer.points,'color');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(s);gl.vertexAttribPointer(s,1,gl.FLOAT,false,24,8);gl.enableVertexAttribArray(c);gl.vertexAttribPointer(c,3,gl.FLOAT,false,24,12);gl.drawArrays(gl.POINTS,0,values.length/6);}
     raf=requestAnimationFrame(draw);
   };
   raf=requestAnimationFrame(draw);
   return()=>{stopped=true;cancelAnimationFrame(raf);gl.deleteBuffer(renderer.buffer);gl.deleteProgram(renderer.points);gl.deleteProgram(renderer.lines);};
 },[layout,addresses,scoped,root,selected,asset,isolate,nodeContext,visibleSet,balance,motion]);
 const selectAt=event=>{if(!pointer.current)return;const dx=event.clientX-pointer.current.x,dy=event.clientY-pointer.current.y;const p=pointer.current;pointer.current=null;if(Math.abs(dx)+Math.abs(dy)>5)return;const rect=event.currentTarget.getBoundingClientRect();const x=event.clientX-rect.left,y=event.clientY-rect.top;let match='',best=26;for(const node of projected.current){const dist=Math.hypot(node.x-x,node.y-y);if(dist<best){best=dist;match=node.id;}}if(match)setSelected(match);};
 const focus=()=>{const q=norm(search);const match=addresses.find(a=>a.includes(q));if(q&&match)setSelected(match);};
 const selectedDetails=useMemo(()=>edges.filter(e=>e.from===selected||e.to===selected).slice(0,5),[edges,selected]);
 const metrics=useMemo(()=>({incoming:edges.filter(e=>e.to===selected).length,outgoing:edges.filter(e=>e.from===selected).length,peers:new Set(edges.filter(e=>e.from===selected||e.to===selected).flatMap(e=>[e.from,e.to]).filter(a=>a!==selected)).size}),[edges,selected]);
 return <section className="overflow-hidden rounded-2xl border border-slate-700 bg-[#08111e]">
  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 p-4"><div><p className="text-xs uppercase tracking-widest text-cyan-300">Unified WebGL network</p><h2 className="mt-1 text-xl font-semibold text-white">Wallet bubble investigation</h2><p className="mt-1 text-xs text-slate-400">{addresses.length} wallets · {scoped.length} observed transfers · layout computed off-thread</p></div><div className="flex flex-wrap items-center gap-2"><button type="button" className="secondary-button" aria-pressed={motion} onClick={()=>setMotion(value=>!value)}>{motion?'Pause flow':'Animate flow'}</button><button type="button" className="secondary-button" onClick={()=>{camera.current={yaw:.1,pitch:-.12,zoom:1};zoomTarget.current=1;setSelected('');setIsolate(false);}}>Reset view</button><input aria-label="Find graph wallet" className={headerClass} placeholder="Wallet address" value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>e.key==='Enter'&&focus()}/><button type="button" onClick={focus} className="secondary-button">Focus</button><select aria-label="Graph asset" className={headerClass} value={asset} onChange={e=>setAsset(e.target.value)}>{assets.map(a=><option key={a}>{a}</option>)}</select></div></div>
  {error&&<p role="alert" className="px-4 py-2 text-amber-300">{error}</p>}
  <div className="grid lg:grid-cols-[minmax(0,1fr)_310px]"><div className="relative overflow-hidden bg-[radial-gradient(ellipse_at_50%_42%,rgba(14,116,144,0.14),transparent_58%),linear-gradient(155deg,#09182c_0%,#050d19_100%)]"><div aria-hidden="true" className="pointer-events-none absolute inset-0 opacity-30" style={{backgroundImage:"linear-gradient(rgba(94,178,215,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(94,178,215,.07) 1px,transparent 1px)",backgroundSize:"46px 46px",maskImage:"radial-gradient(ellipse at center,black,transparent 76%)"}}/><canvas ref={canvasRef} className="relative h-[590px] w-full touch-none cursor-grab lg:h-[720px]" aria-label="Interactive GPU-rendered 3D wallet bubbles" onPointerDown={e=>{pointer.current={x:e.clientX,y:e.clientY,yaw:camera.current.yaw,pitch:camera.current.pitch};e.currentTarget.setPointerCapture?.(e.pointerId);}} onPointerMove={e=>{if(!pointer.current)return;camera.current.yaw=pointer.current.yaw+(e.clientX-pointer.current.x)*.007;camera.current.pitch=clamp(pointer.current.pitch+(e.clientY-pointer.current.y)*.006,-1.2,1.2);}} onPointerUp={selectAt} onPointerCancel={()=>{pointer.current=null;}} onWheel={e=>{e.preventDefault();zoomTarget.current=clamp((zoomTarget.current??camera.current.zoom)*(e.deltaY>0?.9:1.1),.08,5);}}/><div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">{importantLabels.map(id=><div key={id} ref={element=>{if(element)labelRefs.current.set(id,element);else labelRefs.current.delete(id);}} className={`absolute left-0 top-0 whitespace-nowrap rounded-md border px-2 py-1 font-mono text-[10px] shadow-lg backdrop-blur-md ${id===selected?'border-amber-400/50 bg-amber-950/80 text-amber-100':id===root?'border-cyan-400/40 bg-cyan-950/80 text-cyan-100':'border-slate-600/70 bg-slate-950/80 text-slate-200'}`}>{id===root?'ROOT · ':id===selected?'SELECTED · ':''}{short(id)}</div>)}</div><div className="absolute right-4 top-4 z-10 flex flex-col gap-2"><button type="button" aria-label="Zoom in" className="rounded-lg border border-cyan-300/20 bg-slate-950/90 px-3 py-2 text-lg text-white hover:border-cyan-300/60" onClick={()=>{zoomTarget.current=clamp((zoomTarget.current??camera.current.zoom)*1.25,.08,5);}}>+</button><button type="button" aria-label="Zoom out" className="rounded-lg border border-cyan-300/20 bg-slate-950/90 px-3 py-2 text-lg text-white hover:border-cyan-300/60" onClick={()=>{zoomTarget.current=clamp((zoomTarget.current??camera.current.zoom)*.8,.08,5);}}>−</button></div><div className="pointer-events-none absolute left-4 top-4 rounded-xl border border-cyan-300/15 bg-[#071525]/85 px-4 py-3 shadow-xl backdrop-blur-sm"><p className="text-[10px] font-semibold uppercase tracking-[.2em] text-cyan-300">Live evidence network</p><p className="mt-1 text-xs text-slate-300">Drag to orbit · Scroll to zoom · Tap a node · Flow particles show recorded transfer direction</p></div><div className="pointer-events-none absolute bottom-4 left-4 flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-[#071525]/85 px-3 py-2 text-[11px] text-slate-300 backdrop-blur-sm"><span><span className="text-cyan-300">●</span> Root wallet</span><span><span className="text-emerald-300">●</span> Verified label</span><span><span className="text-amber-300">●</span> Selected</span><span><span className="text-violet-300">●</span> Other wallets</span></div></div>
   <aside className="space-y-4 border-t border-slate-700 p-5 lg:border-l lg:border-t-0"><h3 className="text-lg font-semibold text-white">Wallet evidence</h3>{selected?<><p className="break-all font-mono text-xs text-cyan-300">{selected}</p><div className="rounded-xl border border-cyan-400/20 p-3"><p className="text-xs text-slate-400">Live ETH balance</p>{loading?<p>Loading balance…</p>:balance?.unavailable?<p className="text-amber-300">Provider unavailable</p>:balance?<p className="text-2xl font-semibold text-white">{Number(balance.balance_eth??balance.eth??0).toLocaleString(undefined,{maximumFractionDigits:8})} ETH</p>:<p>Not requested</p>}</div><div className="grid grid-cols-2 gap-2 text-sm text-slate-300"><p>Incoming: {metrics.incoming}</p><p>Outgoing: {metrics.outgoing}</p><p>Peers: {metrics.peers}</p></div>{selectedDetails.length>0&&<div className="space-y-2 border-t border-slate-700 pt-3"><p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Observed evidence · first 5</p>{selectedDetails.map(e=><a key={e.id} href={e.tx.evidence_url||('https://etherscan.io/tx/'+e.tx.hash)} target="_blank" rel="noopener noreferrer" className="block rounded-lg border border-slate-700 bg-slate-900/60 p-2 hover:border-cyan-500/50"><span className="block text-[11px] text-slate-300">{e.from===selected?'Outgoing ↗':'Incoming ↙'} · {e.asset}</span><span className="block truncate font-mono text-[11px] text-cyan-300">{short(e.tx.hash)} ↗</span></a>)}</div>}{onExpandAddress&&selected!==root&&!expandedAddresses.map(norm).includes(selected)&&<button type="button" disabled={Boolean(expandingAddress)} onClick={()=>onExpandAddress(selected)} className="primary-button w-full">Expand observed hop</button>}<a href={'https://etherscan.io/address/'+selected} target="_blank" rel="noreferrer" className="text-cyan-300 underline">Verify on Etherscan ↗</a><button type="button" className="secondary-button w-full" onClick={()=>setIsolate(v=>!v)}>{isolate?'Show full graph':'Isolate wallet'}</button></>:<p className="text-sm text-slate-400">Select a bubble to inspect its live balance and observed counterparties.</p>}<p className="text-xs leading-5 text-slate-500">Positions represent observed graph structure only. Neither distances nor risk colors prove ownership, taint, or wrongdoing.</p></aside>
  </div></section>;
}
