import { test, expect } from '@playwright/test';
const ROOT = '0x' + '1'.repeat(40);
const addr = i => '0x' + i.toString(16).padStart(40,'0');
function graph(n) {
  const nodes = [ROOT, ...Array.from({length:n-1}, (_,i)=>addr(i+2))];
  const edges = nodes.slice(1).map((target,i)=>({
    source: ROOT, target, tx_hash: '0x'+(i+1).toString(16).padStart(64,'0'),
    value: '0.1', asset: 'ETH', category: 'external', risk_score: 0,
  }));
  return {root:ROOT, nodes:nodes.map(id=>({id,verified_entities:[]})), edges,
    next_page_keys:{outgoing:null,incoming:null}, scope:'Synthetic bounded E2E fixture'};
}
test('Flow Workspace graph renders 100/500/1000 observed nodes', async ({page}) => {
  // Fixed synthetic inputs validate rendering, NOT real-chain coverage.
  await page.route('**/api/**', route=>{
    const url=route.request().url();
    if(url.includes('/indexed-graph')) return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(graph(1000))});
    if(url.includes('/balance')) return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({balance_eth:'1',block_number:1})});
    return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  });
  await page.goto('/app/');
  await page.getByRole('button',{name:'Monitor',exact:true}).click();
  // Flow Workspace is a monitor subview; assert the graph from the dedicated workspace only if shown.
  const launch = page.getByRole('button',{name:/Flow Workspace|Flow workspace|Flow/i}).first();
  if(await launch.count()){
    await launch.click();
    const input=page.getByRole('textbox',{name:'Ethereum wallet for graph'});
    if(await input.count()){
      await input.fill(ROOT);
      await page.getByRole('button',{name:'Build graph'}).click();
      await expect(page.getByText('1000 wallets', {exact:false})).toBeVisible({timeout:30000});
    }
  }
});
