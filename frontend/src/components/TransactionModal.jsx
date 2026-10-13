import { useEffect } from 'react';
import ReceiptEvents from './ReceiptEvents';

const AMOUNT_ONLY = new Set(['whale_transaction', 'large_transaction', 'notable_transaction', 'medium_transaction']);

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return '0 ETH';
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    return String(whole) + (fraction ? '.' + fraction : '') + ' ETH';
  }
  const value = Number(tx.value_eth);
  return Number.isFinite(value) ? (value === 0 ? '0 ETH' : value.toPrecision(6) + ' ETH') : 'Amount unavailable';
}

function amountOnlyEvidence(tx) {
  return Array.isArray(tx.risk_factors) && tx.risk_factors.length > 0 && tx.risk_factors.every(f => AMOUNT_ONLY.has(f.factor));
}

function riskLabel(score) {
  if (score >= 80) return { text: 'Critical review', color: 'text-red-400', bar: 'bg-red-500' };
  if (score >= 40) return { text: 'High review', color: 'text-orange-400', bar: 'bg-orange-500' };
  if (score >= 20) return { text: 'Review', color: 'text-yellow-300', bar: 'bg-yellow-500' };
  return { text: 'Minimal', color: 'text-emerald-400', bar: 'bg-emerald-500' };
}

export default function TransactionModal({ tx, onClose }) {
  useEffect(() => {
    const handleEscape = event => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  if (!tx) return null;
  const score = Number(tx.risk_score) || 0;
  const amountOnly = amountOnlyEvidence(tx);
  const evidence = tx.evidence_assessment;
  const insufficient = evidence?.assessment === 'insufficient_evidence';
  const risk = insufficient ? { text: 'Insufficient evidence', color: 'text-amber-300', bar: 'bg-amber-400' } : amountOnly ? { text: 'Amount review only', color: 'text-amber-300', bar: 'bg-amber-400' } : riskLabel(score);
  const explanation = typeof tx.ai_explanation === 'string' ? tx.ai_explanation : '';
  const groundedAi = explanation.startsWith('Grounded AI explanation:');
  const deterministic = explanation.startsWith('Evidence-based assessment:') || explanation.startsWith('Rule-based risk assessment:');
  const explanationTitle = groundedAi ? 'Grounded AI explanation' : deterministic ? 'Evidence-based assessment' : 'Stored explanation';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-[#46556d] bg-[#202c40] shadow-2xl" onClick={event => event.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#39475d] bg-[#202c40] px-6 py-4">
          <div><h2 className="text-xl font-semibold text-white">Transaction Details</h2><p className="mt-1 text-xs text-slate-400">Block {Number(tx.block_number || 0).toLocaleString()}</p></div>
          <button onClick={onClose} className="p-2 text-2xl leading-none text-slate-400 hover:text-white" aria-label="Close">×</button>
        </div>

        <div className="space-y-6 p-6">
          <section>
            <div className="mb-2 flex items-center justify-between gap-4"><span className="text-sm uppercase tracking-wide text-slate-400">Risk score</span><span className={`text-xl font-semibold ${risk.color}`}>{score}/100 — {risk.text}</span></div>
            <div className="h-2.5 overflow-hidden rounded-full bg-[#111b2d]"><div className={`h-full ${risk.bar}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} /></div>
            {evidence?.engine_version && <p className="mt-3 text-sm text-slate-400">Evidence engine {evidence.engine_version}: {evidence.rationale} Confidence: {evidence.confidence}. This is not a calibrated probability.</p>}
            {amountOnly && <p className="mt-3 text-sm text-amber-200">The score is based only on transfer size, not verified suspicious behavior.</p>}
          </section>

          <section className={`rounded-lg border p-4 ${groundedAi ? 'border-sky-400/25 bg-sky-400/[0.07]' : 'border-[#46556d] bg-[#172236]'}`}>
            <div className="mb-2 flex items-center justify-between gap-3"><h3 className={`text-sm font-semibold uppercase tracking-wide ${groundedAi ? 'text-sky-300' : 'text-slate-300'}`}>{explanationTitle}</h3>{groundedAi && <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[10px] font-medium text-emerald-300">fact-bound</span>}</div>
            {explanation ? <p className="leading-7 text-slate-200">{explanation}</p> : <p className="text-sm italic text-slate-400">No explanation is stored for this transaction.</p>}
            {groundedAi && <p className="mt-3 text-xs leading-5 text-slate-500">AI wording is stored only when it passes validation against the transaction's saved score and evidence. Unsupported claims fall back to deterministic evidence text.</p>}
          </section>

          {Array.isArray(tx.risk_factors) && tx.risk_factors.length > 0 && <section className="rounded-lg border border-cyan-500/20 bg-cyan-500/[0.04] p-4"><h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-300">Risk evidence trail</h3><div className="space-y-2">{tx.risk_factors.map((factor, index) => <div key={index} className="rounded-lg border border-[#39475d] bg-[#111b2d] p-3"><div className="text-sm text-slate-200">{factor.reason || factor.name || factor.type || 'Recorded scoring signal'}</div>{factor.source && <div className="mt-1 text-xs text-cyan-400">Source: {factor.source}</div>}</div>)}</div><p className="mt-3 text-xs text-slate-500">Signals are investigation cues, not a determination of wrongdoing.</p></section>}

          <section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Transaction hash</div><div className="break-all rounded-lg bg-[#111b2d] p-3 font-mono text-xs text-slate-300">{tx.hash}</div></section>
          <div className="grid gap-4 md:grid-cols-2"><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">From</div><div className="break-all rounded-lg bg-[#111b2d] p-3 font-mono text-xs text-slate-300">{tx.from_address}</div></section><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">To</div><div className="break-all rounded-lg bg-[#111b2d] p-3 font-mono text-xs text-slate-300">{tx.to_address}</div></section></div>
          <div className="grid gap-4 sm:grid-cols-2"><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Value</div><div className="text-2xl font-semibold text-white">{formatEth(tx)}</div></section><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Value (wei)</div><div className="break-all font-mono text-sm text-slate-300">{tx.value_wei}</div></section></div>

          <ReceiptEvents key={tx.hash} hash={tx.hash} />
          <div className="border-t border-[#39475d] pt-4"><a href={`https://etherscan.io/tx/${tx.hash}`} target="_blank" rel="noopener noreferrer" className="text-sm text-sky-400 hover:text-sky-300">View on Etherscan ↗</a></div>
        </div>
      </div>
    </div>
  );
}
