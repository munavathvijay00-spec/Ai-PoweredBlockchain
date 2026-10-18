// Deterministic bounded layout; entirely off the browser's UI thread.
const hash = text => { let h=2166136261; for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0; };
function layout({addresses,links,root}) {
  const count=addresses.length;
  const byId=new Map(addresses.map((a,i)=>[a,i]));
  const degree=new Uint32Array(count);
  const pairs=[];
  for(const link of links){
    const a=byId.get(link[0]), b=byId.get(link[1]);
    if(a===undefined||b===undefined||a===b) continue;
    degree[a]++;degree[b]++;pairs.push([a,b]);
  }
  const positions=new Float32Array(count*3);
  const rootIndex=byId.get(root)??0;
  const sorted=addresses.map((a,i)=>({a,i,d:degree[i]})).filter(x=>x.i!==rootIndex).sort((a,b)=>b.d-a.d||a.a.localeCompare(b.a));
  const ringCapacity=34;
  sorted.forEach(({a,i},rank)=>{
    const ring=Math.floor(rank/ringCapacity);
    const within=rank%ringCapacity;
    const total=Math.min(ringCapacity, sorted.length-ring*ringCapacity);
    const angle=(within/Math.max(1,total))*Math.PI*2+ring*.44+(hash(a)%100)/550;
    const radius=108+ring*112;
    positions[i*3]=Math.cos(angle)*radius;
    positions[i*3+1]=Math.sin(angle)*radius*.82;
    positions[i*3+2]=((hash(a+'z')%1000)/1000-.5)*Math.min(170,75+ring*18);
  });
  // Approximate local collision relaxation: 16 passes, spatial hash, O(n) average.
  const cellSize=65;
  for(let pass=0;pass<16;pass++){
    const grid=new Map();
    for(let i=0;i<count;i++){
      const x=positions[i*3],y=positions[i*3+1];
      const gx=Math.floor(x/cellSize),gy=Math.floor(y/cellSize);
      const key=gx+','+gy;
      if(!grid.has(key))grid.set(key,[]);
      grid.get(key).push(i);
    }
    for(let i=0;i<count;i++){
      if(i===rootIndex)continue;
      const idx=i*3,x=positions[idx],y=positions[idx+1],gx=Math.floor(x/cellSize),gy=Math.floor(y/cellSize);
      for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){
        for(const j of grid.get((gx+dx)+','+(gy+dy))||[]){
          if(j<=i)continue;
          let vx=x-positions[j*3],vy=y-positions[j*3+1];
          const distance=Math.hypot(vx,vy);
          if(distance>=48)continue;
          if(distance<.01){ const theta=(hash(addresses[i]+addresses[j])%6283)/1000;vx=Math.cos(theta);vy=Math.sin(theta); }
          const scale=(48-Math.max(1,distance))*.18/Math.max(1,distance);
          positions[idx]+=vx*scale;positions[idx+1]+=vy*scale;
          if(j!==rootIndex){positions[j*3]-=vx*scale;positions[j*3+1]-=vy*scale;}
        }
      }
    }
  }
  // Camera fits the exact output bounds, not a guessed fixed radius.
  let maxX=80,maxY=80;
  for(let i=0;i<count;i++){
    const x=positions[i*3],y=positions[i*3+1];
    if(!Number.isFinite(x)||!Number.isFinite(y)){positions[i*3]=0;positions[i*3+1]=0;}
    maxX=Math.max(maxX,Math.abs(positions[i*3])+30);
    maxY=Math.max(maxY,Math.abs(positions[i*3+1])+30);
  }
  return {positions,bounds:{x:maxX,y:maxY},degree};
}
self.onmessage=event=>{
  const {seq,payload}=event.data;
  try{const result=layout(payload);self.postMessage({seq,...result},[result.positions.buffer,result.degree.buffer]);}
  catch(error){self.postMessage({seq,error:String(error?.message||error)});}
};
