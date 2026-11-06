function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : '—';
}

export default function StatsBar({ stats, coverage, onMetric }) {
  const flaggedThreshold = Number(stats?.flagged_threshold ?? 20);
  const evidenceSummaries = Number(coverage?.native_transactions?.stored_transactions ?? stats?.total_transactions ?? 0);

  const cards = stats ? [
    { key: 'all', label: 'Retained transfers', value: formatNumber(coverage?.native_transactions?.stored_transactions ?? stats.total_transactions), accent: 'cs-stat-primary', note: 'Show all retained transactions' },
    { key: 'addresses', label: 'Observed addresses', value: formatNumber(stats.total_addresses), accent: 'cs-stat-primary', note: 'Open wallet intelligence' },
    { key: 'flagged', label: `Flagged (≥${flaggedThreshold})`, value: formatNumber(stats.flagged_transactions), accent: 'cs-stat-warning', note: 'Open review queue' },
    { key: 'risk', label: 'Mean review score', value: Number.isFinite(Number(stats.avg_risk_score)) ? Number(stats.avg_risk_score).toFixed(2) : '—', accent: 'cs-stat-primary', note: 'Sort highest risk first' },
    { key: 'evidence', label: 'Retained evidence', value: formatNumber(evidenceSummaries), accent: 'cs-stat-primary', note: 'Retained evidence available for review' },
  ] : null;

  const loadingCards = Array.from({ length: 5 }, (_, index) => ({ loading: true, key: `loading-${index}` }));

  return (
    <div className="cs-stat-grid grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" aria-busy={!cards}>
      {(cards || loadingCards).map((card) => card.loading ? (
        <div key={card.key} className="metric-card" aria-hidden="true">
          <div className="h-3 w-28 animate-pulse rounded bg-slate-700" />
          <div className="mt-4 h-8 w-24 animate-pulse rounded bg-slate-700" />
        </div>
      ) : (
        <button
          key={card.label}
          type="button"
          onClick={() => onMetric?.(card.key)}
          aria-label={`${card.label}: ${card.value}. ${card.note}`}
          className="metric-card cs-stat-card text-left focus-visible:outline focus-visible:outline-2"
        >
          <p className="metric-label">{card.label}</p>
          <p className={`cs-stat-value mt-3 text-[29px] font-semibold leading-none tracking-tight ${card.accent}`}>{card.value}</p>
          {card.note && <p className="cs-stat-note mt-3 text-[11px] text-slate-500">{card.note}</p>}
        </button>
      ))}
    </div>
  );
}
