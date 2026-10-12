import ReceiptEvents from './ReceiptEvents';
function formatEth(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    const amount = BigInt(String(tx.value_wei));
    if (amount === 0n) return '0 ETH';
    const whole = amount / 1000000000000000000n;
    const fraction = (amount % 1000000000000000000n).toString().padStart(18, '0').replace(/0+$/, '');
    return String(whole) + (fraction ? '.' + fraction : '') + ' ETH';
  }
  const value = Number(tx.value_eth);
  if (!Number.isFinite(value)) return 'Amount unavailable';
  return value === 0 ? '0 ETH' : value.toPrecision(6) + ' ETH';
}

/**
 * Modal popup showing full transaction details + AI explanation.
 */
import { useEffect } from 'react';

const AMOUNT_ONLY = new Set(['whale_transaction', 'large_transaction', 'notable_transaction', 'medium_transaction']);

function amountOnlyEvidence(tx) {
  return Array.isArray(tx.risk_factors) && tx.risk_factors.length > 0 &&
    tx.risk_factors.every(f => AMOUNT_ONLY.has(f.factor));
}

function riskLabel(score) {
  if (score >= 80) return { text: 'Critical', color: 'text-red-500' };
  if (score >= 40) return { text: 'High', color: 'text-orange-500' };
  if (score >= 20) return { text: 'Medium', color: 'text-yellow-500' };
  return { text: 'Low', color: 'text-green-500' };
}

function riskBarColor(score) {
  if (score >= 80) return 'bg-red-500';
  if (score >= 40) return 'bg-orange-500';
  if (score >= 20) return 'bg-yellow-500';
  return 'bg-green-500';
}

export default function TransactionModal({ tx, onClose }) {
  useEffect(() => {
    function handleEscape(e) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  if (!tx) return null;

  const amountOnly = amountOnlyEvidence(tx);
  const risk = amountOnly ? { text: 'Amount review only', color: 'text-amber-300' } : riskLabel(tx.risk_score);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-800 rounded-2xl border border-slate-700 max-w-3xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between sticky top-0 bg-slate-800 z-10">
          <div>
            <h2 className="text-xl font-bold text-white">Transaction Details</h2>
            <p className="text-slate-400 text-xs mt-1">Block {tx.block_number.toLocaleString()}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-2xl leading-none p-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {/* Risk Score */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-slate-400 text-sm uppercase tracking-wide">Risk Score</span>
              <span className={`text-2xl font-bold ${risk.color}`}>
                {tx.risk_score}/100 — {risk.text}
              </span>
            </div>
            {amountOnly && <p className="text-amber-200 text-sm mb-3" role="note">This score is based only on transfer size, not verified suspicious behavior. It is not a calibrated probability or evidence of wrongdoing. Historical scores will be revised when the new risk engine is deployed.</p>}
            <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
              <div
                className={`h-full ${amountOnly ? 'bg-amber-400' : riskBarColor(tx.risk_score)} transition-all`}
                style={{ width: `${tx.risk_score}%` }}
              />
            </div>
          </div>

          {/* AI Explanation */}
          {tx.ai_explanation ? (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-blue-400 text-lg">🧠</span>
                <span className="text-blue-400 font-semibold text-sm uppercase tracking-wide">
                  {tx.ai_explanation.startsWith('Rule-based risk assessment:') ? 'Evidence-based assessment' : 'AI-assisted assessment'}
                </span>
              </div>
              <p className="text-slate-200 leading-relaxed">{tx.ai_explanation}</p>
            </div>
          ) : (
            <div className="bg-slate-700/30 border border-slate-700 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-slate-400 text-lg">🧠</span>
                <span className="text-slate-400 font-semibold text-sm uppercase tracking-wide">
                  AI Analysis
                </span>
              </div>
              <p className="text-slate-400 text-sm italic">
                No explanation is stored for this transaction.
              </p>
            </div>
          )}

          {/* Verifiable scoring evidence */}
          {Array.isArray(tx.risk_factors) && tx.risk_factors.length > 0 && (
            <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-300 mb-3">Risk evidence trail</h3>
              <div className="space-y-2">
                {tx.risk_factors.map((factor, i) => (
                  <div key={i} className="rounded-lg bg-slate-900/70 border border-slate-700 p-3">
                    <div className="text-sm text-slate-200">{factor.reason || factor.name || factor.type || 'Recorded scoring signal'}</div>
                    {factor.tx_hash && <div className="font-mono text-xs text-slate-400 break-all mt-1">Evidence tx: {factor.tx_hash}</div>}
                    {factor.source && <div className="text-xs text-cyan-400 mt-1">Source: {factor.source}</div>}
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-500 mt-3">Signals are indicators for investigation, not a determination of wrongdoing.</p>
            </div>
          )}

          {/* Transaction Hash */}
          <div>
            <div className="text-slate-400 text-sm uppercase tracking-wide mb-2">Transaction Hash</div>
            <div className="bg-slate-900 rounded-lg p-3 font-mono text-xs text-slate-300 break-all">
              {tx.hash}
            </div>
          </div>

          {/* From / To */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-slate-400 text-sm uppercase tracking-wide mb-2">From</div>
              <div className="bg-slate-900 rounded-lg p-3 font-mono text-xs text-slate-300 break-all">
                {tx.from_address}
              </div>
            </div>
            <div>
              <div className="text-slate-400 text-sm uppercase tracking-wide mb-2">To</div>
              <div className="bg-slate-900 rounded-lg p-3 font-mono text-xs text-slate-300 break-all">
                {tx.to_address}
              </div>
            </div>
          </div>

          {/* Value */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-slate-400 text-sm uppercase tracking-wide mb-2">Value (ETH)</div>
              <div className="text-2xl font-bold text-white">
                {formatEth(tx)}
              </div>
            </div>
            <div>
              <div className="text-slate-400 text-sm uppercase tracking-wide mb-2">Value (wei)</div>
              <div className="text-sm font-mono text-slate-300 break-all">
                {tx.value_wei}
              </div>
            </div>
          </div>

          <ReceiptEvents key={tx.hash} hash={tx.hash} />

          {/* External link */}
          <div className="pt-4 border-t border-slate-700">
            <a
              href={`https://etherscan.io/tx/${tx.hash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 text-sm"
            >
              View on Etherscan ↗
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}