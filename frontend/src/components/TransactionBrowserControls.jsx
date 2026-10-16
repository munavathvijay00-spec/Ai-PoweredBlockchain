import { useEffect } from 'react';

export default function TransactionBrowserControls({
  search, setSearch, minRisk, setMinRisk, maxRisk, setMaxRisk,
  minValue, setMinValue, maxValue, setMaxValue, sort, setSort,
  pageSize, setPageSize, page, totalPages, onPage, onReset, onExport,
  onQueue,
}) {
  const field = 'rounded-lg border border-[#56657a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-300 focus:ring-2 focus:ring-sky-300';
  const queueButton = 'rounded-lg border px-3 py-2 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-sky-300';

  useEffect(() => {
    const reset = () => onReset?.();
    window.addEventListener('chainscope-clear-filters', reset);
    return () => window.removeEventListener('chainscope-clear-filters', reset);
  }, [onReset]);

  return <section className="platform-card p-5" aria-label="Analyst filters sorting export and pagination">
    <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div><h2 className="text-base font-semibold text-white">Analyst Filters & Triage</h2><p className="mt-1 text-xs text-slate-400">Search, filter, sort, export, or jump directly into a risk queue.</p></div>
      <div className="flex flex-wrap gap-2" aria-label="Risk queue shortcuts">
        <button type="button" onClick={() => onQueue?.('all')} className={`${queueButton} border-slate-500 bg-slate-800 text-slate-100`}>All</button>
        <button type="button" onClick={() => onQueue?.('review')} className={`${queueButton} border-yellow-400/40 bg-yellow-400/[0.10] text-yellow-100`}>◆ Review 20–39</button>
        <button type="button" onClick={() => onQueue?.('high')} className={`${queueButton} border-orange-400/40 bg-orange-400/[0.10] text-orange-100`}>▲ High 40–79</button>
        <button type="button" onClick={() => onQueue?.('critical')} className={`${queueButton} border-red-400/40 bg-red-400/[0.10] text-red-100`}>● Critical 80+</button>
      </div>
    </div>

    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <label className="text-xs font-medium text-slate-200">Search hash or address<input aria-label="Search transaction hash or address" value={search} onChange={event => setSearch(event.target.value)} placeholder="0x..." className={`mt-1 w-full ${field}`} /></label>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs font-medium text-slate-200">Min risk<input aria-label="Minimum risk score" type="number" min="0" max="100" value={minRisk} onChange={event => setMinRisk(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
        <label className="text-xs font-medium text-slate-200">Max risk<input aria-label="Maximum risk score" type="number" min="0" max="100" value={maxRisk} onChange={event => setMaxRisk(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs font-medium text-slate-200">Min ETH<input aria-label="Minimum transaction value in ETH" type="number" min="0" step="0.0001" value={minValue} onChange={event => setMinValue(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
        <label className="text-xs font-medium text-slate-200">Max ETH<input aria-label="Maximum transaction value in ETH" type="number" min="0" step="0.0001" value={maxValue} onChange={event => setMaxValue(event.target.value)} className={`mt-1 w-full ${field}`} /></label>
      </div>
      <label className="text-xs font-medium text-slate-200">Sort<select aria-label="Sort review clusters" value={sort} onChange={event => setSort(event.target.value)} className={`mt-1 w-full ${field}`}><option value="risk_desc">Highest risk first</option><option value="risk_asc">Lowest risk first</option><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="value_desc">Highest value</option><option value="value_asc">Lowest value</option></select></label>
    </div>

    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#46566f] pt-4">
      <div className="flex flex-wrap gap-2"><button onClick={onReset} className="workspace-chip" type="button">Reset filters</button><button onClick={() => onExport('csv')} className="rounded-lg border border-sky-400/40 bg-sky-400/10 px-3 py-2 text-xs font-semibold text-sky-100 hover:bg-sky-400/15 focus:outline-none focus:ring-2 focus:ring-sky-300" type="button">↓ Export CSV</button><button onClick={() => onExport('json')} className="rounded-lg border border-violet-400/40 bg-violet-400/10 px-3 py-2 text-xs font-semibold text-violet-100 hover:bg-violet-400/15 focus:outline-none focus:ring-2 focus:ring-violet-300" type="button">↓ Export JSON</button></div>
      <div className="flex flex-wrap items-center gap-2" aria-label="Pagination controls"><label className="text-xs text-slate-300">Rows<select aria-label="Rows per page" value={pageSize} onChange={event => setPageSize(Number(event.target.value))} className={`ml-2 ${field}`}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><button type="button" onClick={() => onPage(1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="First page">First</button><button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous page">Previous</button><span className="rounded-md bg-[#0d1728] px-3 py-2 text-xs font-medium text-slate-200" aria-live="polite">Page {page} of {Math.max(1, totalPages)}</span><button type="button" onClick={() => onPage(page + 1)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next page">Next</button><button type="button" onClick={() => onPage(totalPages)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Last page">Last</button></div>
    </div>
  </section>;
}
