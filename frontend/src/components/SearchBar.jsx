export default function SearchBar({ value, onChange }) {
  return (
    <div className="search-shell">
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400"><path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="m21 21-4.35-4.35m1.35-5.65a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z" /></svg>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder="Search by hash or address..." aria-label="Search transactions by hash or address" className="min-w-0 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500" />
      {value && <button onClick={() => onChange('')} className="rounded px-2 py-1 text-slate-500 hover:text-white" aria-label="Clear search">×</button>}
    </div>
  );
}
