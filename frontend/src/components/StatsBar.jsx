import { useEffect, useState } from 'react';
import { api } from '../api/client';
import AIProofPanel from './AIProofPanel';

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : '—';
}

export default function StatsBar({ stats, coverage }) {
  const [aiStatus, setAiStatus] = useState(null);
  const flaggedThreshold = Number(stats?.flagged_threshold ?? 20);
  const groundedAi = Number(stats?.ai_generated_explanations ?? 0);
  const evidenceSummaries = Number(coverage?.native_transactions?.stored_transactions ?? stats?.total_transactions ?? 0);

  useEffect(() => {
    let active = true;
    api.getAIStatus()
      .then(result => { if (active) setAiStatus(result); })
      .catch(() => { if (active) setAiStatus(null); });
    return () => { active = false; };
  }, [groundedAi]);

  const cards = stats ? [
    { label: 'Total transactions', value: formatNumber(coverage?.native_transactions?.stored_transactions ?? stats.total_transactions), accent: 'text-[#57a4ff]' },
    { label: 'Addresses tracked', value: formatNumber(stats.total_addresses), accent: 'text-[#c17cff]' },
    { label: `Flagged (≥${flaggedThreshold})`, value: formatNumber(stats.flagged_transactions), accent: 'text-[#ff6969]' },
    { label: 'Avg risk score', value: Number.isFinite(Number(stats.avg_risk_score)) ? Number(stats.avg_risk_score).toFixed(2) : '—', accent: 'text-[#ffd21f]' },
    {
      label: 'Evidence summaries',
      value: formatNumber(evidenceSummaries),
      accent: 'text-[#45db83]',
      note: `Grounded AI accepted: ${formatNumber(groundedAi)}`,
    },
  ] : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        {(cards || [0, 1, 2, 3, 4]).map((card, index) => (
          <div key={card?.label || index} className="metric-card">
            {card ? <>
              <p className="metric-label">{card.label}</p>
              <p className={`mt-2 text-[29px] font-semibold leading-none tracking-tight ${card.accent}`}>{card.value}</p>
              {card.note && <p className="mt-2 text-[11px] text-slate-500">{card.note}</p>}
            </> : <>
              <div className="h-3 w-28 animate-pulse rounded bg-slate-700" />
              <div className="mt-4 h-8 w-24 animate-pulse rounded bg-slate-700" />
            </>}
          </div>
        ))}
      </div>
      <AIProofPanel status={aiStatus} />
    </div>
  );
}
