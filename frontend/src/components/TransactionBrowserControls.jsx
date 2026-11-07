import { useEffect, useState } from 'react';

export default function TransactionBrowserControls({
  search, setSearch, minRisk, setMinRisk, maxRisk, setMaxRisk,
  minValue, setMinValue, maxValue, setMaxValue, sort, setSort,
  pageSize, setPageSize, page, totalPages, onPage, onReset, onExport,
  onQueue,
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const field = 'cs-filter-input rounded-md border px-3 py-2.5 text-sm text-slate-100 outline-none';
  const queueButton = 'cs-queue-pill rounded-md border px-3 py-2 text-xs font-medium transition';

  useEffect(() => {
    const reset = () => onReset?.();
    window.addEventListener('chainscope-clear-filters', reset);
    return () => window.removeEventListener('chainscope-clear-filters', reset);
  }, [onReset]);

  const activeAdvanced = [minRisk, maxRisk, minValue, maxValue].filter(value => value !== '').length;
  return <section className="platform-card cs-filter-panel p-5" aria-label="Analyst filters sorting export and pagination">
    <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div><span className="cs-section-kicker">01 / TRIAGE CONTROLS</span><h2 className="text-base font-semibold text-white">Find the evidence that matters</h2><p className="mt-1 text-xs text-slate-400">Choose a review tier or search a known address. Scores are rules, not fraud probabilities.</p></div>
      <div className="flex flex-wrap gap-2" aria-label="Risk queue shortcuts">
        <button type="button" onClick={() => onQueue?.('all')} className={`${queueButton} cs-queue-all`}>All</button>
        <button type="button" onClick={() => onQueue?.('review')} className={`${queueButton} cs-queue-review`}>Review · 20–39</button>
        <button type="button" onClick={() => onQueue?.('high')} className={`${queueButton} cs-queue-high`}>High · 40–79</button>
        <button type="button" onClick={() => onQueue?.('critical')} className={`${queueButton} cs-queue-critical`}>Critical · 80+</button>
      </div>
    </div>

    <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
      <label className="text-xs font-medium text-slate-200">Search hash or address<input aria-label="Search transaction hash or address" value={search} onChange={event => setSearch(event.target.value)} placeholder="0x..." className={`mt-1 w-full ${field}`} /></label>
      <label className="text-xs font-medium text-slate-200">Order evidence<select aria-label="Sort review clusters" value={sort} onChange={event => setSort(event.target.value)} className={`mt-1 w-full ${field}`}><option value="risk_desc">Highest risk first</option><option value="risk_asc">Lowest risk first</option><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="value_desc">Highest value</option><option value="value_asc">Lowest value</option></select></label>
    </div>
    <button type="button" aria-expanded={advancedOpen} aria-controls="cs-advanced-filters" onClick={() => setAdvancedOpen(value => !value)} className="cs-advanced-toggle">{advancedOpen ? '− Hide' : '+ Show'} precise filters {activeAdvanced ? `· ${activeAdvanced} active` : ''}</button>
    <div id="cs-advanced-filters" className={`cs-advanced-fields gap-3 md:grid-cols-2 ${advancedOpen ? 'grid' : 'hidden'}`}>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs font-medium text-slate-200">Min risk<input aria-label="Minimum risk score" type="number" min="0" max="100" value={minRisk} onChange={event => setMinRisk(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
        <label className="text-xs font-medium text-slate-200">Max risk<input aria-label="Maximum risk score" type="number" min="0" max="100" value={maxRisk} onChange={event => setMaxRisk(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs font-medium text-slate-200">Min ETH<input aria-label="Minimum transaction value in ETH" type="number" min="0" step="0.0001" value={minValue} onChange={event => setMinValue(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
        <label className="text-xs font-medium text-slate-200">Max ETH<input aria-label="Maximum transaction value in ETH" type="number" min="0" step="0.0001" value={maxValue} onChange={event => setMaxValue(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
      </div>
    </div>

    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#303b3e] pt-4">
      <div className="flex flex-wrap gap-2"><button onClick={onReset} className="workspace-chip" type="button">Reset filters</button><button onClick={() => onExport('csv')} className="cs-export-button rounded-md border px-3 py-2 text-xs font-medium" type="button">Export CSV</button><button onClick={() => onExport('json')} className="cs-export-button rounded-md border px-3 py-2 text-xs font-medium" type="button">Export JSON</button></div>
      <div className="flex flex-wrap items-center gap-2" aria-label="Pagination controls"><label className="text-xs text-slate-300">Rows<select aria-label="Rows per page" value={pageSize} onChange={event => setPageSize(Number(event.target.value))} className={`ml-2 ${field}`}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><button type="button" onClick={() => onPage(1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="First page">First</button><button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous page">Previous</button><span className="cs-page-count rounded-md px-3 py-2 text-xs font-medium text-slate-200" aria-live="polite">Page {page} of {Math.max(1, totalPages)}</span><button type="button" onClick={() => onPage(page + 1)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next page">Next</button><button type="button" onClick={() => onPage(totalPages)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Last page">Last</button></div>
    </div>
  </section>;
}
