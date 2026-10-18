function dateOf(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (Number.isFinite(n) && n > 1e9) { const d = new Date(n > 1e12 ? n : n * 1000); return Number.isNaN(d.getTime()) ? null : d; }
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}
export default function InvestigationTimeline({ tokenFlow }) {
  const events = (tokenFlow?.edges || []).flatMap(edge => {
    const date = dateOf(edge.block_timestamp || edge.timestamp);
    if (!date || !edge.tx_hash) return [];
    return [{ tx_hash: edge.tx_hash, date, asset: edge.asset, value: edge.value, direction: edge.direction_from_root }];
  }).sort((a,b)=>b.date-a.date).slice(0,40);
  return <section className="panel p-5" id="timeline" aria-labelledby="timeline-title">
    <p className="eyebrow">Timeline</p><h2 id="timeline-title" className="mt-2 text-lg font-semibold text-white">Timestamped observed transfers</h2>
    <p className="mt-2 text-sm text-slate-400">Only provider-indexed token transfers with returned timestamps are shown; missing timestamps and non-indexed history are not inferred.</p>
    {events.length?<div className="mt-4 space-y-2">{events.map((event,i)=><div key={event.tx_hash+'-'+i} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><time className="text-slate-300">{event.date.toLocaleString()}</time><span className="text-slate-300">{event.asset} · {event.direction||'observed'}</span><a href={'https://etherscan.io/tx/'+event.tx_hash} target="_blank" rel="noreferrer" className="text-cyan-300 underline">Evidence ↗</a></div>)}</div>:<p className="mt-4 text-sm text-amber-200">No reliable timestamps available for the loaded token evidence.</p>}
  </section>;
}
