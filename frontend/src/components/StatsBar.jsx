function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : '—';
}

export default function StatsBar({ stats, coverage }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 xl:grid-cols-5 gap-3">
        {[0, 1, 2, 3, 4].map(item => (
          <div key={item} className="panel h-28 animate-pulse">
            <div className="h-3 w-20 rounded bg-slate-800" />
            <div className="mt-5 h-7 w-24 rounded bg-slate-800" />
          </div>
        ))}
      </div>
    );
  }

  const retained = coverage?.native_transactions?.stored_transactions ?? stats.total_transactions;
  const cards = [
    {
      label: 'Recent transactions',
      value: formatNumber(retained),
      note: '30 min retained window',
      accent: 'text-cyan-300',
      icon: '↗',
    },
    {
      label: 'Addresses observed',
      value: formatNumber(stats.total_addresses),
      note: 'Referenced by retained data',
      accent: 'text-violet-300',
      icon: '◉',
    },
    {
      label: 'Review cues',
      value: formatNumber(stats.flagged_transactions),
      note: 'Indicators, not verdicts',
      accent: 'text-rose-300',
      icon: '△',
    },
    {
      label: 'Mean risk score',
      value: stats.avg_risk_score ?? '—',
      note: 'Rule engine / 100',
      accent: 'text-amber-300',
      icon: '∿',
    },
    {
      label: 'Explained records',
      value: formatNumber(stats.explained_transactions),
      note: 'AI or evidence fallback',
      accent: 'text-emerald-300',
      icon: '✦',
    },
  ];

  return (
    <div className="grid grid-cols-2 xl:grid-cols-5 gap-3">
      {cards.map(card => (
        <div key={card.label} className="panel group relative overflow-hidden">
          <div className="absolute -right-5 -top-5 h-20 w-20 rounded-full bg-white/[0.025] transition group-hover:scale-125" />
          <div className="relative flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">{card.label}</p>
              <p className={`mt-3 text-2xl font-semibold tracking-tight ${card.accent}`}>{card.value}</p>
              <p className="mt-2 text-[11px] leading-4 text-slate-500">{card.note}</p>
            </div>
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/5 bg-white/[0.025] text-sm text-slate-400">
              {card.icon}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
