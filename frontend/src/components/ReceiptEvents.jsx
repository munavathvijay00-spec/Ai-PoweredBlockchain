import { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function ReceiptEvents({ hash }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    api.getTransactionEvents(hash).then(
      result => { if (active) setData(result); },
      () => { if (active) setError(true); }
    );
    return () => { active = false; };
  }, [hash]);
  return <section className="rounded-xl border border-slate-700 p-4 space-y-3">
    <h3 className="text-cyan-300 font-semibold">On-chain receipt events</h3>
    <p className="text-xs text-slate-400">Raw units only. Token metadata and protocol identity are unverified.</p>
    {!data && !error && <p role="status">Loading receipt events...</p>}
    {error && <p role="alert">Receipt unavailable. Please retry later.</p>}
    {data && <>
      <p>{data.decoded_count} recognized events from {data.total_logs} logs.</p>
      {data.truncated && <p>Results truncated to 500 logs.</p>}
      {data.events.map((event, index) => <div key={index} className="rounded-lg bg-slate-900 p-3 text-xs break-all">
        <strong>{event.standard}: {event.event}</strong>
        <pre className="whitespace-pre-wrap mt-2">{JSON.stringify(event, null, 2)}</pre>
      </div>)}
    </>}
  </section>;
}
