# ChainScope robustness target

This document tracks the production hardening target for the intelligence pipeline.

## Acceptance criteria

1. Canonical ingestion exposes checkpoint height/hash, head height, block lag, last successful ingest time, RPC failures, and integrity halts.
2. Historical wallet investigations can use provider-backed, cursor-paginated Ethereum history without pretending the live retention database is complete history.
3. Entity attribution is source-attributed, confidence-scoped, and never inferred from an unlabeled address.
4. Behavioral risk is evidence-first and evaluated only against independently labeled cases; precision/recall are not product claims until a representative validation set exists.
5. AI explanations are optional rewrites of deterministic evidence, cite [E#] evidence IDs, and are rejected on unsupported claims.
6. API request latency, DB health, RPC failures, AI outcomes, ingestion lag, and benchmark metrics are observable.

## Product rule

Missing data is never interpreted as benign behavior. A risk score is a review signal, not a fraud verdict.
