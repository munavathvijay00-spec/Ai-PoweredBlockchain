function fmt(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : '—';
}

function pct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '—';
}

export default function AIProofPanel({ status }) {
  if (!status) {
    return <section className="platform-card p-5"><p className="metric-label">Grounded AI runtime proof</p><p className="mt-3 text-sm text-slate-500">AI runtime telemetry is unavailable.</p></section>;
  }

  const q = status.quality || {};
  const ready = Boolean(status.real_grounded_ai_ready);
  const configured = Boolean(status.provider_configured);
  const runtimeVerified = Boolean(status.runtime_verified);

  return (
    <section className="platform-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="metric-label">Grounded AI runtime proof</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {status.provider || 'disabled'}{status.model ? ` · ${status.model}` : ''}
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-medium ${ready ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}>
          {ready ? 'Runtime verified' : configured ? 'Configured, not verified' : 'Provider unavailable'}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          ['Model attempts', fmt(q.model_attempts)],
          ['Accepted', fmt(q.grounded_ai_runs)],
          ['Rejected', fmt(q.grounding_rejections)],
          ['Provider failures', fmt(q.provider_no_output)],
          ['Acceptance rate', pct(q.grounding_acceptance_rate)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-700/80 bg-slate-900/20 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-100">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-2 text-xs text-slate-500">
        <p>Configured: <span className={configured ? 'text-emerald-300' : 'text-amber-300'}>{configured ? 'yes' : 'no'}</span> · Runtime verified: <span className={runtimeVerified ? 'text-emerald-300' : 'text-amber-300'}>{runtimeVerified ? 'yes' : 'no'}</span></p>
        <p>{status.truthfulness_note || 'Accepted means the model output passed ChainScope grounding checks; this is not fraud-detection accuracy.'}</p>
        {!ready && status.readiness_reason && <p className="text-amber-300/80">Reason: {String(status.readiness_reason).replaceAll('_', ' ')}</p>}
      </div>
    </section>
  );
}
