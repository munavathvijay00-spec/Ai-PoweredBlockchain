export default function TransactionBrowserControls({
  search, setSearch, minRisk, setMinRisk, maxRisk, setMaxRisk,
  minValue, setMinValue, maxValue, setMaxValue, sort, setSort,
  pageSize, setPageSize, page, totalPages, onPage, onReset, onExport,
  onQueue,
}) {
  const field = 'rounded-lg border border-[#42516a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20';
  const queueButton = 'rounded-lg border px-3 py-2 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-sky-400/40';
  return (
    <section className="platform-card p-5" aria-label="Analyst filters sorting export and pagination">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Analyst Filters & Triage</h2>
          <p className="mt-1 text-xs text-slate-500">Search, filter, sort, export, or jump directly into a risk queue.</p>
        </div>
        <div className="flex flex-wrap gap-2" aria-label="Risk queue shortcuts">
          <button type="button" onClick={() => onQueue?.('all')} className={`${queueButton} border-slate-600 bg-slate-800 text-slate-200`}>All</button>
          <button type="button" onClick={() => onQueue?.('review')} className={`${queueButton} border-yellow-400/25 bg-yellow-400/[0.08] text-yellow-200`}>🟡 Review 20–39</button>
          <button type="button" onClick={() => onQueue?.('high')} className={`${queueButton} border-orange-400/25 bg-orange-400/[0.08] text-orange-200`}>🟠 High 40–79</button>
          <button type="button" onClick={() => onQueue?.('critical')} className={`${queueButton} border-red-400/25 bg-red-400/[0.08] text-red-200`}>🔴 Critical 80+</button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="text-xs font-medium text-slate-300">Search hash or address
          <input aria-label="Search transaction hash or address" value={search} onChange={e => setSearch(e.target.value)} placeholder="0x..." className={`mt-1 w-full ${field}`} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-medium text-slate-300">Min risk
            <input aria-label="Minimum risk score" type="number" min="0" max="100" value={minRisk} onChange={e => setMinRisk(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
          <label className="text-xs font-medium text-slate-300">Max risk
            <input aria-label="Maximum risk score" type="number" min="0" max="100" value={maxRisk} onChange={e => setMaxRisk(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-medium text-slate-300">Min ETH
            <input aria-label="Minimum transaction value in ETH" type="number" min="0" step="0.0001" value={minValue} onChange={e => setMinValue(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
          <label className="text-xs font-medium text-slate-300">Max ETH
            <input aria-label="Maximum transaction value in ETH" type="number" min="0" step="0.0001" value={maxValue} onChange={e => setMaxValue(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
        </div>
        <label className="text-xs font-medium text-slate-300">Sort
          <select aria-label="Sort transactions" value={sort} onChange={e => setSort(e.target.value)} className={`mt-1 w-full ${field}`}>
            <option value="risk_desc">Highest risk first</option><option value="risk_asc">Lowest risk first</option>
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
            <option value="value_desc">Highest value</option><option value="value_asc">Lowest value</option>
          </select>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#39475d] pt-4">
        <div className="flex flex-wrap gap-2">
          <button onClick={onReset} className="workspace-chip" type="button">Reset filters</button>
          <button onClick={() => onExport('csv')} className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs font-semibold text-sky-200 hover:bg-sky-400/15" type="button">↓ Export CSV</button>
          <button onClick={() => onExport('json')} className="rounded-lg border border-violet-400/30 bg-violet-400/10 px-3 py-2 text-xs font-semibold text-violet-200 hover:bg-violet-400/15" type="button">↓ Export JSON</button>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label="Pagination controls">
          <label className="text-xs text-slate-400">Rows
            <select aria-label="Rows per page" value={pageSize} onChange={e => setPageSize(Number(e.target.value))} className={`ml-2 ${field}`}>
              <option value="25">25</option><option value="50">50</option><option value="100">100</option>
            </select>
          </label>
          <button type="button" onClick={() => onPage(1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="First page">First</button>
          <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous page">Previous</button>
          <span className="rounded-md bg-[#0d1728] px-3 py-2 text-xs font-medium text-slate-300" aria-live="polite">Page {page} of {Math.max(1, totalPages)}</span>
          <button type="button" onClick={() => onPage(page + 1)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next page">Next</button>
          <button type="button" onClick={() => onPage(totalPages)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Last page">Last</button>
        </div>
      </div>
    </section>
  );
}
