import { useEffect, useRef, useState } from 'react';
import { bestAddressLabel } from '../utils/knownContracts';

const AMOUNT_ONLY = new Set(['whale_transaction', 'large_transaction', 'notable_transaction', 'medium_transaction']);

function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return '0 ETH';
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    return `${whole}${fraction ? `.${fraction.slice(0, 8)}` : ''} ETH`;
  }
  const value = Number(tx.value_eth);
  return Number.isFinite(value) ? `${value.toPrecision(6)} ETH` : 'Amount unavailable';
}

function utcLabel(timestamp) {
  if (!timestamp) return 'Unknown UTC time';
  const raw = String(timestamp);
  const explicit = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(explicit);
  return Number.isNaN(date.getTime()) ? 'Unknown UTC time' : `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

function amountOnlyEvidence(tx) {
  return Array.isArray(tx.risk_factors) && tx.risk_factors.length > 0 && tx.risk_factors.every(f => AMOUNT_ONLY.has(f.factor));
}

function riskLabel(score) {
  if (score >= 80) return { text: 'Critical review', color: 'text-red-300', bar: 'bg-red-500' };
  if (score >= 40) return { text: 'High review', color: 'text-orange-300', bar: 'bg-orange-500' };
  if (score >= 20) return { text: 'Review', color: 'text-yellow-200', bar: 'bg-yellow-500' };
  if (score > 0) return { text: 'Low signal', color: 'text-emerald-300', bar: 'bg-emerald-500' };
  return { text: 'No review signal', color: 'text-slate-400', bar: 'bg-slate-600' };
}

function explanationMeta(tx) {
  const explanation = typeof tx.ai_explanation === 'string' ? tx.ai_explanation.trim() : '';
  const status = tx.explanation_status || (
    explanation.startsWith('Grounded AI explanation:') ? 'grounded_ai'
      : explanation.startsWith('Rule-based risk assessment:') || explanation.startsWith('Evidence-based assessment:') || explanation.startsWith('Evidence-based transaction review:') ? 'deterministic'
        : explanation ? 'legacy_unverified' : 'none'
  );
  if (status === 'grounded_ai') return { status, explanation, title: 'Grounded AI explanation', badge: 'fact-bound' };
  if (status === 'deterministic') return { status, explanation, title: 'Deterministic evidence review', badge: 'deterministic' };
  if (status === 'legacy_unverified') return { status, explanation: '', title: 'Legacy explanation withheld', badge: 'unverified' };
  return { status: 'none', explanation: '', title: 'Explanation unavailable', badge: null };
}

function CopyField({ label, value, extra }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }
  return <section>
    <div className="mb-2 flex items-center justify-between gap-2"><span className="text-sm uppercase tracking-wide text-slate-400">{label}</span><button type="button" onClick={copy} className="text-xs text-sky-400 hover:text-sky-300">{copied ? 'Copied' : 'Copy'}</button></div>
    <div className="break-all rounded-lg bg-[#111b2d] p-3 font-mono text-xs text-slate-300">{value || 'N/A'}</div>
    {extra}
  </section>;
}

function EntityContext({ tx }) {
  const context = tx?.entity_context || {};
  const rows = [];
  for (const [role, items] of [['sender', context.sender], ['recipient', context.recipient]]) {
    if (!Array.isArray(items)) continue;
    for (const item of items) rows.push({ role, ...item });
  }
  const senderKnown = bestAddressLabel(tx.from_address, context.sender);
  const recipientKnown = bestAddressLabel(tx.to_address, context.recipient);
  if (!rows.length && !senderKnown && !recipientKnown) return null;
  return <section className="rounded-lg border border-violet-400/20 bg-violet-400/[0.04] p-4">
    <h3 className="text-sm font-semibold uppercase tracking-wider text-violet-300">Address identity context</h3>
    <div className="mt-3 space-y-2">
      {[['sender', tx.from_address, senderKnown], ['recipient', tx.to_address, recipientKnown]].map(([role, address, known]) => known && <div key={role} className="rounded-lg border border-[#39475d] bg-[#111b2d] p-3"><div className="flex flex-wrap items-center gap-2"><span className="rounded border border-violet-400/25 bg-violet-400/10 px-2 py-0.5 text-[10px] uppercase text-violet-200">{role}</span><span className="text-sm font-medium text-white">{known.label}</span><span className="text-xs text-slate-400">{known.type}</span></div><div className="mt-1 break-all font-mono text-[11px] text-slate-500">{address}</div>{known.source && <div className="mt-1 text-[10px] text-slate-500">Source: {known.source}</div>}</div>)}
    </div>
    <p className="mt-3 text-xs text-slate-500">Labels identify exact known addresses only. They do not establish beneficial ownership or transaction intent.</p>
  </section>;
}

export default function TransactionModal({ tx, onClose }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const handleKey = event => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll('button, a, input, textarea, select, [tabindex]:not([tabindex="-1"])')).filter(el => !el.disabled);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', handleKey);
    return () => { document.removeEventListener('keydown', handleKey); previous?.focus?.(); };
  }, [onClose]);

  if (!tx) return null;
  const score = Number(tx.risk_score) || 0;
  const amountOnly = amountOnlyEvidence(tx);
  const evidence = tx.evidence_assessment;
  const insufficient = evidence?.assessment === 'insufficient_evidence';
  const risk = insufficient ? { text: 'Insufficient evidence', color: 'text-amber-300', bar: 'bg-amber-400' } : amountOnly ? { text: 'Amount review only', color: 'text-amber-300', bar: 'bg-amber-400' } : riskLabel(score);
  const explanation = explanationMeta(tx);
  const factors = Array.isArray(tx.risk_factors) ? tx.risk_factors.filter(item => item && typeof item === 'object') : [];
  const selfTransfer = Boolean(tx.relationship_context?.self_transfer) || String(tx.from_address).toLowerCase() === String(tx.to_address).toLowerCase();
  const samePairCount = Number(tx.relationship_context?.same_pair_count || 1);

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="transaction-dialog-title" className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-[#46556d] bg-[#202c40] shadow-2xl">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#39475d] bg-[#202c40] px-6 py-4">
        <div><h2 id="transaction-dialog-title" className="text-xl font-semibold text-white">Transaction Investigation</h2><p className="mt-1 text-xs text-slate-400">Block {Number(tx.block_number || 0).toLocaleString()} · {utcLabel(tx.timestamp)}</p></div>
        <button ref={closeRef} onClick={onClose} className="rounded p-2 text-2xl leading-none text-slate-400 hover:text-white focus:ring-2 focus:ring-sky-400/50" aria-label="Close transaction details">×</button>
      </div>

      <div className="space-y-5 p-6">
        <section className="rounded-lg border border-[#39475d] bg-[#111b2d] p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-4"><span className="text-sm uppercase tracking-wide text-slate-400">Review score</span><span className={`text-xl font-semibold ${risk.color}`}>{score ? `${score}/100` : '—'} · {risk.text}</span></div>
          <div className="h-2.5 overflow-hidden rounded-full bg-[#0b1423]"><div className={`h-full ${risk.bar}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} /></div>
          {evidence?.engine_version && <p className="mt-3 text-sm text-slate-400">Evidence engine {evidence.engine_version}: {evidence.rationale} Confidence: {evidence.confidence}. This is not a calibrated fraud probability.</p>}
          <div className="mt-3 flex flex-wrap gap-2">{selfTransfer && <span className="rounded border border-violet-400/25 bg-violet-400/10 px-2 py-1 text-xs text-violet-200">Self-transfer</span>}{samePairCount > 1 && <span className="rounded border border-sky-400/25 bg-sky-400/10 px-2 py-1 text-xs text-sky-200">Repeated sender-recipient pair ×{samePairCount}</span>}</div>
        </section>

        <section className="rounded-lg border border-cyan-400/25 bg-cyan-400/[0.05] p-4" aria-labelledby="why-flagged-title">
          <h3 id="why-flagged-title" className="text-sm font-semibold uppercase tracking-wider text-cyan-300">Why flagged</h3>
          {factors.length ? <div className="mt-3 space-y-2">{factors.map((factor, index) => <div key={index} className="flex gap-3 rounded-lg border border-[#39475d] bg-[#111b2d] p-3"><span className="shrink-0 rounded border border-cyan-400/25 bg-cyan-400/10 px-2 py-0.5 font-mono text-xs text-cyan-300">E{index + 1}</span><div><p className="text-sm text-slate-100">{factor.reason || factor.name || factor.type || 'Recorded review signal'}</p>{factor.source && <p className="mt-1 text-xs text-cyan-400">Source: {factor.source}</p>}{factor.source_url && <a href={factor.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs text-sky-400">Open cited evidence ↗</a>}</div></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No review factors are recorded for this transaction.</p>}
          {amountOnly && <p className="mt-3 text-xs text-amber-200">Current review score is based only on transfer size, not verified malicious behavior.</p>}
        </section>

        <section className={`rounded-lg border p-4 ${explanation.status === 'grounded_ai' ? 'border-sky-400/25 bg-sky-400/[0.06]' : 'border-emerald-400/20 bg-emerald-400/[0.04]'}`}>
          <div className="mb-2 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold uppercase tracking-wide text-slate-200">{explanation.title}</h3>{explanation.badge && <span className="rounded-full border border-slate-600 bg-slate-800 px-2 py-1 text-[10px] text-slate-300">{explanation.badge}</span>}</div>
          {explanation.explanation ? <p className="leading-7 text-slate-200">{explanation.explanation}</p> : <p className="text-sm italic text-slate-500">No trusted explanation is available.</p>}
        </section>

        <EntityContext tx={tx} />
        <CopyField label="Transaction hash" value={tx.hash} />
        <div className="grid gap-4 md:grid-cols-2"><CopyField label="From" value={tx.from_address} /><CopyField label="To" value={tx.to_address} /></div>
        <div className="grid gap-4 sm:grid-cols-3"><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Value</div><div className="text-xl font-semibold text-white">{formatEth(tx)}</div></section><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Block</div><div className="text-lg font-semibold text-white">{Number(tx.block_number || 0).toLocaleString()}</div></section><section><div className="mb-2 text-sm uppercase tracking-wide text-slate-400">Timestamp</div><div className="text-sm text-slate-200">{utcLabel(tx.timestamp)}</div></section></div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#39475d] pt-4"><p className="text-xs text-slate-500">Evidence-grounded transaction details.</p><a href={`https://etherscan.io/tx/${tx.hash}`} target="_blank" rel="noopener noreferrer" className="text-sm text-sky-400 hover:text-sky-300">View full transaction on Etherscan ↗</a></div>
      </div>
    </div>
  </div>;
}
