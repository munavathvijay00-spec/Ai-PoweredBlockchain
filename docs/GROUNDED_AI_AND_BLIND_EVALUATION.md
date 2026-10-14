# Grounded AI + Independent Evaluation Standard

ChainScope must be able to prove two different things:

1. **AI grounding:** every factual AI claim is traceable to evidence already present in ChainScope's verified transaction/risk evidence.
2. **Detection quality:** detector performance is measured against labels produced independently of ChainScope's prediction logic.

These are separate measurements. A grounded LLM can still explain a poor detector, and an accurate detector can still be explained badly by an LLM.

## 1. Grounded AI contract

The LLM is not a data source. It receives a structured evidence contract containing transaction facts and enumerated evidence items (`E1`, `E2`, ...).

Every generated factual claim must contain one or more evidence IDs. Unknown evidence IDs, uncited claims, missing uncertainty language, or claims produced when no source evidence exists are rejected. Rejected or unavailable model output must fall back to the deterministic evidence explanation.

The production path should therefore be:

`verified chain data -> detector/risk evidence -> evidence contract -> LLM structured claims -> validator -> rendered explanation`

Not:

`transaction -> LLM -> plausible explanation`

The model must never independently infer wallet identity, criminal intent, sanctions status, mixer use, exchange ownership, theft, laundering, or scam status unless that fact is already represented by verified evidence supplied to the contract.

## 2. Blind independent labelled holdout

Do not label the old `labeling_queue.csv` while `predicted_flag` or `detector_signals` are visible. Seeing the prediction can bias ground truth.

Build a blind package:

```bash
python scripts/build_blind_evaluation_set.py evidence.json evaluation/holdout-v1
```

This creates:

- `cases.csv` — factual case information for reviewers.
- `labels.csv` — blank independent adjudication sheet.
- `predictions.csv` — frozen ChainScope output. Keep this hidden from reviewers.
- `manifest.json` — dataset ID and SHA-256 hashes so the exact evaluation set is reproducible.

A reviewer fills only `labels.csv` using evidence independent of ChainScope. Recommended sources include authoritative incident reports, sanctions/designation records, known exploit post-mortems, verified entity attribution, or a documented manual investigation. The label source and evidence URL should be recorded for every positive label and, where practical, for negative controls.

After labeling is complete:

```bash
python scripts/evaluate_blind_holdout.py \
  evaluation/holdout-v1/labels.csv \
  evaluation/holdout-v1/predictions.csv
```

The join happens only at evaluation time by `case_id`.

## 3. Dataset rules

A credible holdout should satisfy all of the following:

- Labels are assigned without seeing ChainScope predictions or detector signals.
- Evaluation cases are not used to tune thresholds or detection rules.
- Duplicate or near-duplicate transactions are controlled so the same incident does not leak across train/tuning/evaluation partitions.
- The set includes positives, normal activity, difficult negatives, and ambiguous cases.
- Ambiguous ground truth should be excluded from the primary binary benchmark or tracked as a separate adjudication state before final scoring.
- Detector version, dataset ID, data window, and evaluation timestamp are recorded with every published metric.

For a serious product claim, prefer a fixed versioned holdout plus a later temporal holdout collected after detector rules were frozen.

## 4. Metrics that matter

Always report support counts with percentages. At minimum report:

- precision
- recall
- F1
- false-positive rate
- false-negative rate
- decision coverage
- abstention rate
- 95% confidence intervals

For an alerting product, a positive abstention is an operational missed alert and is treated accordingly by the evaluator.

Do not present LLM grounding acceptance rate as detector accuracy. They answer different questions.

## 5. Product readiness gate

ChainScope should not claim production-grade AI intelligence until all of these are true:

- at least one real configured LLM produces accepted grounded output on real Ethereum cases;
- unsupported claims are automatically rejected in tests and in the live path;
- AI audit records show provider/model, grounding decision, rejection reason, and fallback behavior;
- a blind independent holdout exists and is versioned;
- reported detector metrics come from that holdout rather than synthetic or self-labelled examples;
- failures and abstentions are visible rather than silently converted into confident conclusions.

This standard is intentionally stricter than a hackathon demo. It is what turns the AI layer from presentation text into an auditable blockchain-intelligence component.
