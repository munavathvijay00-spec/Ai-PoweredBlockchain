function fmt(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : '—';
}

function pct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '—';
}

function metric(value, digits = 3) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

export default function AIProofPanel({ status, mlStatus }) {
  const q = status?.quality || {};
  const ready = Boolean(status?.real_grounded_ai_ready);
  const configured = Boolean(status?.provider_configured);
  const runtimeVerified = Boolean(status?.runtime_verified);

  const mlAvailable = Boolean(mlStatus?.available);
  const mlGate = Boolean(mlStatus?.production_quality_gate_passed);
  const test = mlStatus?.test_metrics || {};
  const mlMode = mlStatus?.deployment_mode || mlStatus?.mode || 'not trained';

  return (
    <section className="platform-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="metric-label">Intelligence runtime proof</p>
          <p className="mt-2 text-lg font-semibold text-white">
            {status?.provider || 'AI disabled'}{status?.model ? ` · ${status.model}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${ready ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}>
            AI: {ready ? 'runtime verified' : configured ? 'configured, not verified' : 'provider unavailable'}
          </span>
          <span className={`rounded-full border px-3 py-1 text-xs font-medium ${mlGate ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : mlAvailable ? 'border-sky-400/30 bg-sky-400/10 text-sky-300' : 'border-slate-700 bg-slate-900 text-slate-400'}`}>
            ML: {mlGate ? 'quality gate passed' : mlAvailable ? mlMode.replaceAll('_', ' ') : 'not trained'}
          </span>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          ['AI attempts', fmt(q.model_attempts)],
          ['AI accepted', fmt(q.grounded_ai_runs)],
          ['AI rejected', fmt(q.grounding_rejections)],
          ['AI failures', fmt(q.provider_no_output)],
          ['Acceptance', pct(q.grounding_acceptance_rate)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-700/80 bg-slate-900/20 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-100">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-5">
        {[
          ['Independent labels', fmt(mlStatus?.dataset_rows)],
          ['Test ROC-AUC', metric(test.roc_auc)],
          ['Test F1', metric(test.f1)],
          ['Test precision', metric(test.precision)],
          ['Brier score', metric(test.brier)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-800 bg-slate-950/35 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
            <p className="mt-2 text-lg font-semibold text-slate-100">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-2 text-xs text-slate-500">
        <p>
          Grounded AI configured: <span className={configured ? 'text-emerald-300' : 'text-amber-300'}>{configured ? 'yes' : 'no'}</span>
          {' · '}runtime verified: <span className={runtimeVerified ? 'text-emerald-300' : 'text-amber-300'}>{runtimeVerified ? 'yes' : 'no'}</span>
          {' · '}ML supervision: <span className="text-sky-300">{mlStatus?.supervision || 'unavailable'}</span>
        </p>
        <p>{status?.truthfulness_note || 'Accepted AI output passed grounding checks; it is not fraud-detection accuracy.'}</p>
        {mlAvailable && <p>ML remains separated from the production rule score unless its independent quality gate is explicitly passed. Dataset fingerprint: <span className="font-mono text-slate-400">{String(mlStatus?.dataset_fingerprint_sha256 || '—').slice(0, 16)}…</span></p>}
        {!ready && status?.readiness_reason && <p className="text-amber-300/80">AI reason: {String(status.readiness_reason).replaceAll('_', ' ')}</p>}
        {mlAvailable && !mlGate && <p className="text-sky-300/80">ML mode: {String(mlMode).replaceAll('_', ' ')} — useful as an independent shadow signal, not yet promoted into production scoring.</p>}
      </div>
    </section>
  );
}