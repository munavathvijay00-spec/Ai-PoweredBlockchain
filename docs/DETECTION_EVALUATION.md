# Detection evaluation protocol

ChainScope currently has **no validated fraud-detection accuracy**. The evaluation tools make that limitation measurable instead of hiding it. They do not create ground truth and they must not be used to turn ChainScope's own flags into labels.

## 1. Freeze a blind evaluation package

Export a ChainScope wallet evidence bundle, then build a leakage-resistant package:

```bash
python scripts/build_blind_evaluation_set.py chainscope-evidence.json eval_package
```

The package deliberately separates what the human reviewer sees from what ChainScope predicted:

- `cases.csv` — factual case material visible to labelers;
- `labels.csv` — blank adjudication sheet with no detector prediction;
- `predictions.csv` — frozen ChainScope predictions; keep this hidden from labelers;
- `manifest.json` — dataset identity and SHA-256 hashes for reproducibility.

Do **not** give `predictions.csv` to the person assigning ground truth. The reviewer should label from independent evidence only.

The older `build_labeling_queue.py` workflow is retained only for compatibility and should not be used for final independent performance claims because it exposes detector output to the reviewer.

## 2. Independent adjudication requirements

For every labeled case, complete:

- `actual_label` — `1` or `0` for the precisely defined target condition;
- `label_source` — independent source or adjudication method;
- `label_evidence_url` — source used to support the label;
- `adjudicator_id` — reviewer identifier;
- `adjudicated_at` — adjudication timestamp.

An unflagged ChainScope transaction is **not** automatically a benign ground-truth case, and a flagged transaction is **not** automatically positive.

## 3. Evaluate only after labels are frozen

Keep human labels and detector predictions separate until evaluation time:

```bash
python -m unittest discover -s tests -p 'test_detection_evaluation.py' -v
python -m unittest discover -s tests -p 'test_blind_holdout.py' -v
python scripts/evaluate_blind_holdout.py \
  eval_package/labels.csv \
  eval_package/predictions.csv \
  eval_package/manifest.json
```

The sealed evaluator:

- rejects duplicate or blank `case_id` values;
- rejects missing labels or predictions;
- requires exact case-ID agreement between files;
- requires independent label provenance fields;
- verifies the frozen `predictions.csv` SHA-256 against the manifest before computing metrics;
- never silently converts abstention into a benign result.

For low-level evaluator testing, `scripts/evaluate_detection.py` still accepts a prejoined CSV with:

```csv
case_id,actual_label,predicted_flag
```

Do not use a manually joined CSV for the final holdout claim when the sealed blind package is available.

## 4. Reported metrics

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
11. Do not publish synthetic examples as measured real-world performance.

## Operational scope

The live ChainScope database is a rolling recent-chain index and the on-demand wallet provider returns bounded, paginated records. Neither is a complete historical corpus. Evaluation datasets therefore need an explicit sampling window and independent evidence retention outside the live rolling store.
