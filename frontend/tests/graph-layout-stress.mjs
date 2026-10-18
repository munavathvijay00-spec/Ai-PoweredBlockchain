import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const code=readFileSync(new URL('../../src/workers/graphLayout.worker.js',import.meta.url),'utf8');
const host={postMessage(message){host.message=message;}};
const context={self:host,Float32Array,Uint32Array,Map,Set,Math,Number,String};
vm.runInNewContext(code,context);
for(const count of [100,500,1000]){
 const root='0x'+(0).toString(16).padStart(40,'0');
 const addresses=Array.from({length:count},(_,i)=>'0x'+i.toString(16).padStart(40,'0'));
 const links=addresses.slice(1).map(address=>[root,address]);
 host.onmessage({data:{seq:1,payload:{addresses,links,root}}});
 const result=host.message;
 assert.equal(result.positions.length,count*3);
 assert.ok(result.bounds.x>0&&result.bounds.y>0);
 assert.ok([...result.positions].every(Number.isFinite));
 const coords=new Set();
 for(let i=0;i<count;i++){coords.add(Math.round(result.positions[i*3])+'-'+Math.round(result.positions[i*3+1]));}
 assert.ok(coords.size>=count*.95,'overlapping graph nodes');
 console.log(count+' nodes: bounded, finite, '+coords.size+' unique positions');
}
