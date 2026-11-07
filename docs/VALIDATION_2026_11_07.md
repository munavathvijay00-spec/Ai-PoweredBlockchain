# ChainScope validation record — 2026-11-07

This record distinguishes **observed results**, **diagnostic baselines**, and
**untested production claims**. It does not certify fraud detection or uptime.

## Detection evaluation

- External dataset: `huggingface:Stepan4545/tx_scam`.
- Sample: 500 rows, selected as 250 positive and 250 negative.
- Source: https://huggingface.co/datasets/Stepan4545/tx_scam
- Source's train split and label methodology are **not independently adjudicated**
  in this report. The balanced sample is **not representative** of contemporary
  Ethereum prevalence, and its labels cannot establish forensic truth.
- Product threshold: 20. Source of measurement: read-only production
  `/api/evaluation/external?threshold=20` on 2026-11-07.

### Deployed evidence-gated detector

| Result | Cases |
| --- | ---: |
| TP / FP / TN / FN (decided) | 0 / 0 / 0 / 0 |
| Positive abstentions | 250 |
| Negative abstentions | 250 |
| Decision coverage | 0% |
| Operational recall (positive abstentions counted as misses) | 0% |
| Precision | **Undefined** |
| False-positive rate | **Undefined** |

All cases lack the history/attribution information required by ChainScope's
evidence gate. Consequently, the system declines to make a positive or negative
judgment. Zero decisions must **not** be reported as zero false-positive rate.

### Amount-only diagnostic, *not* the deployed detector

To expose the limitation of using only native ETH transfer amount, a fixed
`value_wei >= 10 ETH` decision was evaluated on exactly the same stored rows.
This corresponds to the native amount tier crossing the 20-point review
threshold *without* the product evidence/abstention gate. It is an intentionally
incomplete heuristic baseline, **not a change to risk-scoring production logic**.

| TP | FP | TN | FN | Precision | Recall | FPR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 25 | 225 | 234 | 39.02% | 6.40% | 10.00% |

SQL used (read-only):

```sql
WITH predictions AS (
  SELECT label,
    CASE WHEN value_wei_text::numeric >= 10000000000000000000
      THEN 1 ELSE 0 END AS predicted
  FROM external_detection_benchmark_cases
  WHERE source = 'huggingface:Stepan4545/tx_scam'
)
SELECT COUNT(*) AS n,
  COUNT(*) FILTER(WHERE label=1 AND predicted=1) AS tp,
  COUNT(*) FILTER(WHERE label=0 AND predicted=1) AS fp,
  COUNT(*) FILTER(WHERE label=0 AND predicted=0) AS tn,
  COUNT(*) FILTER(WHERE label=1 AND predicted=0) AS fn
FROM predictions;
```

Do not use this dataset to tune thresholds and then advertise performance on
the same records. A separately frozen, independently adjudicated, representative
holdout with full historical context is required for meaningful product metrics.

## Recovery fault drill

Run locally: `python scripts/run_recovery_fault_drill.py`.

Uses the actual `reconcile_competing_worker` function and retry policy, with
in-memory checkpoints and fake RPC clients. No production worker is restarted,
no Neon data is written, and no live RPC calls occur.

| Scenario | Result | Isolated elapsed time |
| --- | --- | ---: |
| Newer canonical checkpoint conflict | Pass | 0.011 ms |
| Noncanonical checkpoint fails closed | Pass | 0.010 ms |
| Worker interruption and new worker reconciliation | Pass | 5.368 ms |
| Two transient RPC failures before success | Pass | 10.310 ms |

The retry-policy waits of 15 and 30 seconds were scaled down to 5 ms in the
isolated test. **These elapsed measurements are not production recovery times.**
Actual end-to-end recovery SLOs require a separate staging service and database
branch, a controlled worker stop, checkpoint verification, and time-to-freshness
measurement under realistic RPC latency and deploy startup behavior.

## Next evidence required

1. Independent adjudicator provenance and both positive/negative labels on a
   locked full-context holdout, separated from any threshold selection sample.
2. Full `pytest` suite and integration tests in an environment with backend
   dependencies installed (not available in this workspace session).
3. Staging interruption drills with measured wall-clock recovery and no
   unverified checkpoint advancement.
4. Production monitoring over time; one healthy checkpoint is not an uptime SLO.
