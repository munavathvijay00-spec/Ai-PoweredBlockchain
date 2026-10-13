# Detection evaluation protocol

ChainScope currently has **no validated fraud-detection accuracy**. The evaluator is an offline scoring utility, not a source of ground-truth labels.

## CSV schema

Prepare a CSV with three required columns:

```csv
case_id,actual_label,predicted_flag
```

- `case_id`: unique, stable case identifier; use anonymized IDs when possible.
- `actual_label`: independently adjudicated ground-truth label, `1` for the target condition and `0` for its absence.
- `predicted_flag`: binary decision produced by a **frozen, documented** ChainScope rule or model; `1` means flagged.
- Never label a case positive simply because ChainScope flagged it.
- Do not publish results from synthetic examples as measured real-world performance.

## Run

From the repository root:

```bash
python -m unittest discover -s tests -p 'test_detection_evaluation.py'
python scripts/evaluate_detection.py path/to/labeled_cases.csv
```

The script reports confusion-matrix counts, precision, recall, specificity, F1, accuracy, false-positive and false-negative rates, and class support. Undefined metrics are `null`, not zero.

## Evaluation requirements

1. Define exactly what the positive label means (for example, a particular *documented* scam behavior, not vague wallet risk).
2. Source independently verified positive and negative cases; retain evidence, chain, block range, and labeling methodology in a separate restricted dataset.
3. Separate training/tuning cases from evaluation cases. Avoid the same wallet, entity, or transaction appearing across splits where it could leak labels.
4. Freeze detection code, threshold, and evaluation period before running the holdout test.
5. Include normal activity and difficult benign lookalikes. Document prevalence and sampling bias.
6. Report case count, class balance, missing data, coverage, confusion matrix, and every metric alongside its denominator.
7. Inspect false positives and false negatives manually, with transaction-level evidence. Repeat on new time periods and data sources.
8. Do not treat a transaction-level benchmark as proof of wallet-level accuracy, or vice versa.

**Operational note:** The production ingestion worker has an unresolved canonical checkpoint mismatch. Its indexed data should not be treated as a complete, up-to-date evaluation corpus.
