export default function FilterTabs({ active, onChange, counts }) {
  const tabs = [
    { id: 'all', label: 'All', count: counts.all, tone: 'text-slate-300' },
    { id: 'flagged', label: 'Flagged', count: counts.flagged, tone: 'text-[#ffd21f]' },
    { id: 'high', label: 'High Risk', count: counts.high, tone: 'text-[#ff6969]' },
  ];
  return (
    <div className="filter-shell" role="tablist" aria-label="Transaction filters">
      {tabs.map(tab => (
        <button key={tab.id} role="tab" aria-selected={active === tab.id} onClick={() => onChange(tab.id)} className={`filter-tab ${active === tab.id ? 'filter-tab-active' : ''}`}>
          <span>{tab.label}</span><span className={`filter-count ${tab.tone}`}>{tab.count}</span>
        </button>
      ))}
    </div>
  );
}
