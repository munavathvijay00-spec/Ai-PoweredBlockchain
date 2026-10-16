export default function TransactionBrowserControls({
  search, setSearch, minRisk, setMinRisk, maxRisk, setMaxRisk,
  minValue, setMinValue, maxValue, setMaxValue, sort, setSort,
  pageSize, setPageSize, page, totalPages, onPage, onReset, onExport,
}) {
  const field = 'rounded-lg border border-[#39475d] bg-[#101b2e] px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20';
  return (
    <section className="platform-card p-4" aria-label="Transaction filters and pagination">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="text-xs text-slate-400">Search hash or address
          <input aria-label="Search transaction hash or address" value={search} onChange={e => setSearch(e.target.value)} placeholder="0x..." className={`mt-1 w-full ${field}`} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-400">Min risk
            <input aria-label="Minimum risk score" type="number" min="0" max="100" value={minRisk} onChange={e => setMinRisk(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
          <label className="text-xs text-slate-400">Max risk
            <input aria-label="Maximum risk score" type="number" min="0" max="100" value={maxRisk} onChange={e => setMaxRisk(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-400">Min ETH
            <input aria-label="Minimum transaction value in ETH" type="number" min="0" step="0.0001" value={minValue} onChange={e => setMinValue(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
          <label className="text-xs text-slate-400">Max ETH
            <input aria-label="Maximum transaction value in ETH" type="number" min="0" step="0.0001" value={maxValue} onChange={e => setMaxValue(e.target.value)} className={`mt-1 w-full ${field}`} />
          </label>
        </div>
        <label className="text-xs text-slate-400">Sort
          <select aria-label="Sort transactions" value={sort} onChange={e => setSort(e.target.value)} className={`mt-1 w-full ${field}`}>
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
            <option value="risk_desc">Highest risk</option><option value="risk_asc">Lowest risk</option>
            <option value="value_desc">Highest value</option><option value="value_asc">Lowest value</option>
          </select>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#39475d] pt-4">
        <div className="flex flex-wrap gap-2">
          <button onClick={onReset} className="workspace-chip" type="button">Reset filters</button>
          <button onClick={() => onExport('csv')} className="workspace-chip" type="button">Export CSV</button>
          <button onClick={() => onExport('json')} className="workspace-chip" type="button">Export JSON</button>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label="Pagination controls">
          <label className="text-xs text-slate-400">Rows
            <select aria-label="Rows per page" value={pageSize} onChange={e => setPageSize(Number(e.target.value))} className={`ml-2 ${field}`}>
              <option value="25">25</option><option value="50">50</option><option value="100">100</option>
            </select>
          </label>
          <button type="button" onClick={() => onPage(1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="First page">First</button>
          <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous page">Previous</button>
          <span className="px-2 text-xs text-slate-400" aria-live="polite">Page {page} of {Math.max(1, totalPages)}</span>
          <button type="button" onClick={() => onPage(page + 1)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next page">Next</button>
          <button type="button" onClick={() => onPage(totalPages)} disabled={page >= totalPages} className="workspace-chip disabled:cursor-not-allowed disabled:opacity-40" aria-label="Last page">Last</button>
        </div>
      </div>
    </section>
  );
}
