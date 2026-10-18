import { test, expect } from '@playwright/test';
const ROOT = '0x' + '1'.repeat(40);
const addr = i => '0x' + i.toString(16).padStart(40,'0');
function graph(n) {
  const addresses = [ROOT, ...Array.from({length:n-1},(_,i)=>addr(i+2))];
  return {root:ROOT, nodes:addresses.map(id=>({id,verified_entities:[]})), edges:addresses.slice(1).map((target,i)=>({
    source:ROOT,target,tx_hash:'0x'+(i+1).toString(16).padStart(64,'0'),
    value:'0.1',asset:'ETH',category:'external'
  })),scope:'Synthetic test evidence',next_page_keys:{incoming:null,outgoing:null}};
}
for(const count of [100,500,1000]) {
  test('canonical Investigate can render '+count+' synthetic wallet nodes',async ({page})=>{
    await page.route('**/api/**',route=>{
      const url=route.request().url();
      let body={};
      if(url.includes('/indexed-graph'))body=graph(count);
      else if(url.includes('/fund-flow'))body={directed_paths:[],token_flow:{available:false,edges:[],assets:[]},entity_exposures:[],flow_summary:{observed_incoming_wei:'0',observed_outgoing_wei:'0'}};
      else if(url.includes('/coverage-summary'))body={coverage_grade:'bounded',coverage_statement:'Synthetic fixture'};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto('/app/');
    await page.getByRole('textbox',{name:'Ethereum wallet address'}).fill(ROOT);
    await page.getByRole('button',{name:'Investigate wallet'}).click();
    await expect(page.getByText(count+' wallets', {exact:false})).toBeVisible({timeout:30000});
    await expect(page.getByLabel('Interactive GPU-rendered 3D wallet bubbles')).toBeVisible({timeout:30000});
  });
}
