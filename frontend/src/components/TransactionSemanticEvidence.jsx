import { useState } from 'react';
import { api } from '../api/client';

export default function TransactionSemanticEvidence({ findings = [] }) {
  const [selected, setSelected] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  if (!findings.length) return null;
  const inspect = async hash => {
    setSelected(hash);setReceipt(null);setError('');setLoading(true);
    try { const result=await api.getReceiptEvidence(hash);setReceipt(result); }
    catch(e){setError(e?.status===404?'Receipt not found on Ethereum mainnet.':e?.message||'Receipt verification unavailable.');}
    finally{setLoading(false);}
  };
  return <section className="panel p-5" aria-labelledby="semantic-title">
    <p className="eyebrow">Verified transaction semantics</p>
    <h2 id="semantic-title" className="mt-2 text-lg font-semibold text-white">On-chain evidence and execution receipts</h2>
    <p className="mt-2 text-sm leading-6 text-slate-400">Loaded transfer observations are leads. Verify a transaction to request its actual Ethereum mainnet receipt, execution status and emitted event candidates.</p>
    <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full min-w-[750px] text-left text-sm">
        <thead className="bg-slate-950/60 text-xs text-slate-500"><tr><th className="p-3">Loaded evidence</th><th className="p-3">Token contracts</th><th className="p-3">Transfers</th><th className="p-3">Verification</th></tr></thead>
        <tbody>{findings.slice(0,25).map(item=><tr key={item.tx_hash} className="border-t border-slate-800">
          <td className="p-3 text-white">{String(item.classification||'unknown').replaceAll('_',' ')}</td>
          <td className="p-3 text-slate-300">{item.distinct_token_contracts?.length||0}</td>
          <td className="p-3 text-slate-300">{item.token_edges_observed||0} token · {item.native_edges_observed||0} native</td>
          <td className="p-3"><button type="button" onClick={()=>inspect(item.tx_hash)} disabled={loading} className="text-cyan-300 underline disabled:opacity-50">Inspect receipt</button> · <a href={item.evidence_url} target="_blank" rel="noreferrer" className="text-sky-300 underline">Etherscan ↗</a></td>
        </tr>)}</tbody>
      </table>
    </div>
    {selected&&<div className="mt-4 rounded-xl border border-cyan-400/15 bg-slate-950/40 p-4" role="region" aria-label="Verified transaction receipt">
      <p className="break-all font-mono text-xs text-cyan-300">{selected}</p>
      {loading&&<p role="status" className="mt-2 text-sm text-slate-300">Verifying transaction and receipt…</p>}
      {error&&<p role="alert" className="mt-2 text-sm text-amber-200">{error}</p>}
      {receipt&&<>
        <p className="mt-3 text-sm text-white">Execution: <strong>{receipt.receipt_status}</strong> · Block {Number(receipt.block_number).toLocaleString()} · Gas used {receipt.gas_used}</p>
        <p className="mt-2 text-sm text-slate-300">Observed event candidates: {receipt.decoded_event_candidates?.length||0} · Ambiguous events skipped: {receipt.skipped_ambiguous_events||0}</p>
        {(receipt.decoded_event_candidates||[]).slice(0,12).map((event,i)=><div key={i} className="mt-2 rounded border border-slate-700 p-3 text-xs text-slate-300">
          <p className="text-white">{String(event.kind).replaceAll('_',' ')}</p>
          <p className="mt-1 break-all">Contract {event.emitter_contract}</p><p className="break-all">{event.from_or_owner} → {event.to_or_spender}</p><p>Raw units: {event.raw_uint256}</p>
        </div>)}
        <p className="mt-3 text-xs text-amber-200">{receipt.coverage} Swaps and bridges are not marked confirmed from a receipt alone.</p>
      </>}
    </div>}
    <p className="mt-3 text-xs text-amber-200">Contract ABI, token standard, decimals and internal execution paths require additional verification. Co-occurrence is not proof of a swap or bridge.</p>
  </section>;
}
