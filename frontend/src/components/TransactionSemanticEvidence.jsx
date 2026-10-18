export default function TransactionSemanticEvidence({ findings = [] }) {
  if (!findings.length) return null;
  return <section className="panel p-5" aria-labelledby="semantic-title">
    <p className="eyebrow">Transaction semantics</p>
    <h2 id="semantic-title" className="mt-2 text-lg font-semibold text-white">What the loaded transactions actually establish</h2>
    <p className="mt-2 text-sm leading-6 text-slate-400">These are contract/token transfer observations. A completed swap, bridge or internal execution path is not claimed unless verified execution evidence supports it.</p>
    <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead className="bg-slate-950/60 text-xs text-slate-500"><tr><th className="p-3">Classification</th><th className="p-3">Token contracts</th><th className="p-3">Observed transfers</th><th className="p-3">Evidence</th></tr></thead>
        <tbody>{findings.slice(0, 25).map(item => <tr key={item.tx_hash} className="border-t border-slate-800">
          <td className="p-3 text-white">{String(item.classification || 'unknown').replaceAll('_', ' ')}</td>
          <td className="p-3 text-slate-300">{item.distinct_token_contracts?.length || 0}</td>
          <td className="p-3 text-slate-300">{item.token_edges_observed || 0} token · {item.native_edges_observed || 0} native</td>
          <td className="p-3"><a href={item.evidence_url} target="_blank" rel="noreferrer" className="text-cyan-300 underline">Verify ↗</a></td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="mt-3 text-xs text-amber-200">Co-occurrence is not proof of swap execution, bridge activity, asset conservation or ownership.</p>
  </section>;
}
