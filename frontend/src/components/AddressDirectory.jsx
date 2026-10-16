import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { knownContract } from '../utils/knownContracts';

function shortAddress(value) {
  if (!value) return 'N/A';
  return value.length <= 21 ? value : `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function utc(value) {
  if (!value) return '—';
  const raw = String(value);
  const explicit = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(explicit);
  return Number.isNaN(date.getTime()) ? '—' : `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

export default function AddressDirectory({ onInvestigate }) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('activity_desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [data, setData] = useState({ addresses: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setLoading(true); setError('');
      try {
        const result = await api.getAddressBrowser({ limit: pageSize, offset: (page - 1) * pageSize, search, sort });
        if (active) setData(result);
      } catch (err) {
        if (active) setError(err?.message || 'Unable to load tracked addresses.');
      } finally {
        if (active) setLoading(false);
      }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [search, sort, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(Number(data.total || 0) / pageSize));
  const start = data.addresses?.length ? (page - 1) * pageSize + 1 : 0;
  const end = data.addresses?.length ? start + data.addresses.length - 1 : 0;

  return (
    <section className="platform-card overflow-hidden" aria-labelledby="address-directory-title">
      <div className="border-b border-[#39475d] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div><h2 id="address-directory-title" className="text-lg font-semibold text-white">Tracked Address Directory</h2><p className="mt-1 text-sm text-slate-400">Showing {start.toLocaleString()}–{end.toLocaleString()} of {Number(data.total || 0).toLocaleString()} addresses.</p></div>
          <div className="flex flex-wrap gap-2"><label className="text-xs text-slate-400">Search<input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} placeholder="Address or label" className="ml-2 rounded-lg border border-[#42516a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100" /></label><label className="text-xs text-slate-400">Sort<select value={sort} onChange={event => { setSort(event.target.value); setPage(1); }} className="ml-2 rounded-lg border border-[#42516a] bg-[#0d1728] px-3 py-2 text-sm text-slate-100"><option value="activity_desc">Most active</option><option value="recent">Recently seen</option><option value="oldest">Oldest tracked</option><option value="risk_desc">Highest address score</option></select></label></div>
        </div>
      </div>

      {loading && <div className="p-8 text-center text-sm text-slate-400" role="status">Loading tracked addresses…</div>}
      {!loading && error && <div className="p-8 text-center text-sm text-rose-300">{error}</div>}
      {!loading && !error && !data.addresses?.length && <div className="p-8 text-center text-sm text-slate-500">No tracked addresses match this search.</div>}

      {!loading && !error && data.addresses?.length > 0 && <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-[#39475d] bg-[#111d31] text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-4 py-3">Address</th><th className="px-4 py-3">Activity</th><th className="px-4 py-3">First seen</th><th className="px-4 py-3">Last seen</th><th className="px-4 py-3">Action</th></tr></thead><tbody className="divide-y divide-[#39475d]">{data.addresses.map(row => { const known = knownContract(row.address); return <tr key={row.address} className="hover:bg-white/[0.025]"><td className="px-4 py-3"><div className="font-mono text-xs text-slate-200" title={row.address}>{shortAddress(row.address)}</div>{(known || row.label) && <div className="mt-1 text-[10px] text-sky-300">{row.label || known?.label}{known?.type ? ` · ${known.type}` : ''}</div>}</td><td className="px-4 py-3 text-slate-300"><span className="font-semibold text-white">{Number(row.tx_count || 0).toLocaleString()}</span><span className="ml-2 text-xs text-slate-500">{Number(row.outgoing_count || 0).toLocaleString()} out · {Number(row.incoming_count || 0).toLocaleString()} in</span></td><td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{utc(row.first_seen)}</td><td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{utc(row.last_seen)}</td><td className="px-4 py-3"><button type="button" onClick={() => onInvestigate?.(row.address)} className="workspace-chip">Investigate</button></td></tr>; })}</tbody></table></div>}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#39475d] p-4"><label className="text-xs text-slate-400">Rows<select value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1); }} className="ml-2 rounded-lg border border-[#42516a] bg-[#0d1728] px-2 py-1 text-sm text-slate-100"><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><div className="flex items-center gap-2"><button type="button" onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="workspace-chip disabled:opacity-40">Previous</button><span className="text-xs text-slate-400">Page {page} of {totalPages}</span><button type="button" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages} className="workspace-chip disabled:opacity-40">Next</button></div></div>
    </section>
  );
}
