# Grounded AI evaluation protocol

ChainScope's language model is an explanation layer, not a source of blockchain facts. The production grounding gate must reject rewrites that invent unsupported claims, numbers, evidence references, or transaction context.

This evaluation is separate from fraud/detection accuracy. A model can be perfectly grounded and still summarize a weak detector; likewise, a detector can be accurate while an explanation model hallucinates.

## What is measured

Use `scripts/evaluate_grounded_ai.py` with an independently authored JSONL holdout set.

Each case contains:

```json
{"case_id":"g-001","baseline":"...","candidate":"...","expected_grounded":true,"tx":{}}
```

- `baseline`: deterministic ChainScope source-of-truth explanation.
- `candidate`: model-generated explanation being evaluated.
- `expected_grounded`: independent human label stating whether the candidate is a faithful rewrite.
- `tx`: optional transaction context used by the production grounding checker.

Do **not** create `expected_grounded` from ChainScope's own `grounding_report` result. That would make the benchmark circular.

## Required benchmark categories

A representative holdout should include both faithful rewrites and adversarial failures:

1. faithful paraphrase preserving evidence references;
2. invented numeric claim;
3. invented evidence reference;
4. missing required evidence reference;
5. unsupported mixer/exchange/sanctions/scam/hack attribution;
6. overclaim such as "confirmed fraud";
7. wrong transaction-specific hash, address, block, or amount;
8. generic response that loses transaction specificity;
9. safe abstention when supporting factors are unavailable;
10. difficult benign wording that should still be accepted.

## Metrics

The evaluator reports:

- grounded acceptance precision;
- grounded acceptance recall;
- unsupported-claim rejection rate;
- false-accept rate;
- false-reject rate;
- overall acceptance/rejection rates;
- rejection reason counts.

A low false-accept rate is especially important because false acceptance means unsupported content was allowed through the grounding gate.

## Holdout discipline

- Write benchmark cases independently of the grounding implementation where possible.
- Keep tuning cases separate from the final holdout set.
- Freeze the grounding code/version before running final metrics.
- Include natural model outputs, not only synthetic adversarial sentences.
- Preserve the provider, model, prompt version, timestamp, and source evidence for every real model run.
- Report sample size and class balance with every metric.
- Never describe grounding accuracy as fraud-detection accuracy.

## Run

```bash
pytest tests/unit/test_grounded_ai_benchmark.py -v
python scripts/evaluate_grounded_ai.py path/to/grounding_holdout.jsonl
```

The target is not an impressive number by itself. The target is a reproducible benchmark where unsupported claims are demonstrably rejected and every accepted explanation remains traceable to deterministic evidence.
