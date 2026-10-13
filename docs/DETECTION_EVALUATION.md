# Detection evaluation protocol

ChainScope currently has **no validated fraud-detection accuracy**. The evaluation tools make that limitation measurable instead of hiding it. They do not create ground truth and they must not be used to turn ChainScope's own flags into labels.

## 1. Freeze an evidence sample

Export a wallet evidence bundle from ChainScope, then create an independent labeling queue:

```bash
python scripts/build_labeling_queue.py chainscope-evidence.json labeling_queue.csv
```

The queue freezes transaction evidence and ChainScope's current `predicted_flag`, but intentionally leaves these columns blank:

- `actual_label`
- `label_source`
- `label_evidence_url`
- `label_notes`

A reviewer must fill those fields from evidence independent of ChainScope. An unflagged ChainScope transaction is **not** automatically a benign ground-truth case.

## 2. Evaluation CSV schema

The evaluator requires at least:

```csv
case_id,actual_label,predicted_flag
```

- `case_id`: unique, stable case identifier; use anonymized IDs when possible.
- `actual_label`: independently adjudicated ground-truth label, `1` for the precisely defined target condition and `0` for its absence.
- `predicted_flag`: `1`, `0`, or `abstain`. Aliases `review`, `clear`, and `insufficient_evidence` are accepted.
- Never label a case positive simply because ChainScope flagged it.
- Do not publish results from synthetic examples as measured real-world performance.

## 3. Run the evaluator

```bash
python -m unittest discover -s tests -p 'test_detection_evaluation.py' -v
python -m unittest discover -s tests -p 'test_labeling_queue.py' -v
python scripts/evaluate_detection.py path/to/labeled_cases.csv
```

The evaluator reports:

- confusion-matrix counts;
- precision, operational recall, specificity, F1 and accuracy;
- false-positive and false-negative rates;
- abstention count/rate and decision coverage;
- recall on decided cases separately from operational recall;
- positive and negative class support;
- 95% Wilson confidence intervals for key rates.

Undefined metrics are `null`, never fabricated as zero.

## Abstention semantics

ChainScope can explicitly abstain when evidence is insufficient. Evaluation keeps that behavior visible:

- a **positive abstention** is counted as an operational missed alert for recall/FNR;
- a **negative abstention** remains an abstention and is not silently converted into a true negative;
- decision-only metrics are reported separately so high performance on a tiny decided subset cannot masquerade as broad coverage.

## Evaluation requirements

1. Define exactly what the positive label means, such as a documented scam behavior rather than vague "wallet risk".
2. Source independently verified positive and negative cases; retain evidence, chain, block range, reviewer and labeling methodology in a restricted dataset.
3. Separate tuning cases from holdout evaluation cases. Prevent the same wallet, entity, campaign or transaction from leaking across splits.
4. Freeze detection code, threshold, rule version and evaluation period before running the holdout test.
5. Include normal activity and difficult benign lookalikes. Document prevalence and sampling bias.
6. Report case count, class balance, missing data, coverage, abstention rate, confusion matrix and metric denominators.
7. Inspect false positives, false negatives and abstentions manually with transaction-level evidence.
8. Repeat evaluation on new time periods and, where possible, independent data sources.
9. Do not treat a transaction-level benchmark as proof of wallet-level accuracy, or vice versa.
10. Do not describe entity-source matches as fraud-detection accuracy. Source attribution and behavior detection are separate claims.

## Operational scope

The live ChainScope database is a rolling recent-chain index and the on-demand wallet provider returns bounded, paginated records. Neither is a complete historical corpus. Evaluation datasets therefore need an explicit sampling window and independent evidence retention outside the live rolling store.
