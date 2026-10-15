# ChainScope Blind Evaluation Protocol

## Purpose

This protocol measures the quality of ChainScope's deterministic blockchain review signals without allowing model or detector output to influence human ground-truth labels.

The goal is to support defensible claims about precision, recall, F1, false positives, false negatives, specificity and confusion-matrix counts. It is not a fraud-verdict benchmark and must not be presented as proof that a wallet or transaction is criminal.

## Evaluation unit

A **case** is a transaction/event observation inside a clearly documented evidence window. Labels apply only to the target condition defined for that case and window.

A negative label means **the target review condition was not independently substantiated within the defined evidence window**. It must never be described as proof that a wallet is globally safe or benign.

## Required workflow

### 1. Freeze the detector

Before any holdout labels are revealed:

- Record the detector/rules version or Git commit.
- Do not tune thresholds, rules or features using the holdout labels.
- Generate detector predictions once for the frozen case set.

### 2. Build the blind package

Run:

```bash
python scripts/build_blind_evaluation_set.py evidence.json evaluation/run-001
```

The package contains:

- `cases.csv` — factual case material visible to labelers.
- `labels.csv` — blank adjudication sheet visible to labelers.
- `predictions.csv` — detector output; keep sealed from labelers.
- `manifest.json` — dataset ID, protocol declaration and SHA-256 file hashes.

Only `cases.csv` and `labels.csv` may be shared with adjudicators.

### 3. Independent adjudication

Each completed label must contain:

- `case_id`
- `actual_label` (`0` or `1`)
- `label_source`
- `label_evidence_url`
- `adjudicator_id`
- `adjudicated_at`
- optional notes

The label must be based on evidence independent of ChainScope's detector prediction. Labelers must not see `predicted_flag`, detector signals, risk scores produced by the detector, or model-generated explanations.

Prefer two independent adjudicators where practical. Conflicts should be resolved using a documented third-party or senior adjudication step without revealing the detector prediction.

### 4. Freeze labels

After adjudication:

- stop editing the case set;
- record the final label file;
- preserve its provenance;
- do not alter detector output to fit the labels.

### 5. Verify sealed predictions and evaluate

Run:

```bash
python scripts/evaluate_blind_holdout.py \
  evaluation/run-001/labels.csv \
  evaluation/run-001/predictions.csv \
  evaluation/run-001/manifest.json
```

The evaluator must abort if:

- case IDs do not match exactly;
- labels are incomplete;
- label provenance is missing;
- duplicate case IDs exist;
- the manifest does not declare blind independent adjudication;
- the sealed `predictions.csv` SHA-256 no longer matches the manifest.

Only after these checks pass are labels and predictions joined by `case_id`.

## Metrics

Report at minimum:

- True positives (TP)
- False positives (FP)
- True negatives (TN)
- False negatives (FN)
- Precision
- Recall
- F1 score
- Specificity
- Accuracy
- False-positive rate
- False-negative rate
- Abstention count/rate where applicable
- 95% confidence intervals where available

Always show the raw confusion-matrix counts next to percentage metrics.

## Publication gate

Do not publish headline detector-quality metrics unless the independently labeled holdout contains at least:

- **30 total cases**
- **10 positive cases**
- **10 negative cases**

Larger and more diverse holdouts are strongly preferred. A positive-only seed set is useful for pipeline validation but is insufficient for defensible precision, specificity or false-positive claims.

## Leakage controls

The following are prohibited before labels are frozen:

- showing labelers `predicted_flag`;
- showing labelers detector signal names;
- showing labelers detector-produced risk scores;
- giving labelers ChainScope AI explanations for the same case;
- tuning the detector using holdout labels;
- selecting only detector-positive cases and calling the result a balanced evaluation set.

## Grounded AI evaluation is separate

Detector accuracy and AI-grounding quality are different measurements.

For AI explanations, ChainScope should report separately:

- percentage of generated summaries accepted by the evidence validator;
- percentage rejected/abstained;
- unsupported numeric-claim rejection rate;
- unsupported sensitive-claim rejection rate;
- citation validity rate;
- provider/model/version used.

A grounded explanation can faithfully describe a wrong detector signal, so grounding acceptance must never be presented as detector precision or recall.

## Reproducibility record

Each published evaluation should retain:

- dataset ID;
- detector commit/version;
- case-generation procedure;
- label provenance;
- adjudication date;
- manifest hashes;
- evaluation script version/commit;
- full confusion matrix;
- publication-gate status.

This makes the result reproducible and prevents post-hoc metric editing.
