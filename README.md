# ChainScope — Ethereum Blockchain Intelligence (Research Prototype)

**Status:** Deployed research/portfolio prototype · **Network:** Ethereum mainnet (chain ID 1) · **Detection accuracy:** not established · **Not a fraud verdict or compliance decision system**

[Current application (Railway)](https://ai-poweredblockchain-production.up.railway.app/app/) · [OpenAPI documentation](https://ai-poweredblockchain-production.up.railway.app/docs)

ChainScope is a full-stack Ethereum transaction analysis and wallet investigation workspace. It ingests a bounded set of on-chain transactions, displays provenance-linked evidence, draws observed transfer networks, computes **rule-based review-priority signals**, supports analyst case tracking and can optionally draft tightly constrained AI explanations. It is **not** a substitute for complete chain forensics, independent sanctions screening, or professionally validated detection.

> **Evidence and freshness warning:** A successful deployment or a dashboard badge does not guarantee complete or canonical blockchain coverage. Before relying on a result, check `/api/coverage`, the latest checkpoint against the canonical RPC block hash, evidence links, and any per-wallet pagination or sync limitations.

## Live functionality and verification status

| Capability | Implementation | What is and isn't verified |
|---|---|---|
| Ethereum ingestion | PostgreSQL transaction store and separate ingestion worker | A progressing checkpoint and recent rows were observed on 2026-10-18; continued canonical-chain correctness and recovery still need repeatable validation. |
| Wallet investigation | Bounded external, token and other provider-supported transfer-category retrieval; counterparty exploration | Wallet-specific coverage varies by API response, category, provider, pagination and cache. No full-history guarantee. |
| 3D flow graph | React + custom WebGL canvas, layout worker, wallet selection and Etherscan evidence links | Links are observed transfer relationships, **not** shared ownership. Large-graph FPS and accessibility need testing. |
| Risk indicators | Deterministic factors and scores (0–100); default flagged threshold 20 | **Not calibrated fraud probabilities**. Detection precision, recall, FPR and false negatives have not been demonstrated on a representative independent holdout. |
| AI explanations | Optional Ollama / Groq provider with structured evidence validation and deterministic fallback | Provider/model can vary by environment. Model output must not be treated as verified source facts. No published hallucination benchmark or demonstrated advantage over deterministic summaries. |
| Case management | Role-protected cases, evidence attachments, status changes, audit trail and JSON reports | Code deployed; authenticated browser E2E, permissions, integrity and recovery tests remain outstanding. |
| API protections | Authentication/RBAC for privileged actions, signed sessions, request size limits, rate-limit middleware, configurable CORS | Presence of controls is not a security audit. Public reads can reveal queried targets in provider and operational logs. |
| Test and operations tooling | Python tests, component tests, read-only ingest diagnostic and endpoint probe | No trustworthy repository-wide coverage % or production load-test results are claimed here. |

## P0: ingestion integrity and safe recovery

The README previously claimed **the production ingestion worker was blocked by a canonical checkpoint mismatch**. That was a historical observation, **not a verified current outage**: on 2026-10-18, live PostgreSQL checks showed advancing block heights and checkpoint updates, and the deployed dashboard displayed newer indexed blocks. **A full canonical hash comparison and sustained-ingestion verification have not yet been completed**, so uninterrupted correctness must not be inferred.

For a read-only integrity diagnosis, execute **in an environment that can access both PostgreSQL and the Ethereum RPC**:

```bash
python -m scripts.diagnose_ingestion
```

The diagnostic checks the saved checkpoint height/hash against the provider's block hash and reports lag. A mismatch should **fail closed**: inspect worker/RPC logs, find a provable retained common ancestor, verify the relevant reorg window and replay through supported ingestion logic. **Never delete evidence, set an arbitrary checkpoint, or mark a mismatch resolved solely to make the UI green.** Retention limits may make full backfill impossible; document gaps.

Also inspect `GET /api/coverage` for retained block range, transaction timestamps, counts, checkpoint age, history categories and coverage limitations. A recent cursor timestamp proves activity, not completeness.

## Detection quality: unmeasured until independently evaluated

`GET /api/flagged?min_score=20` returns **review-priority matches**, not transactions established to be fraudulent. The threshold 20 is a configurable operational cutoff and is **not a calibrated risk probability**. A score of 80 does **not** mean an 80% chance of fraud.

The repository includes an evaluation harness and endpoints under `/api/evaluation` for independently sourced labels. Use an independent, disjoint holdout; audit source leakage, class balance and label quality; disclose thresholds, class support, precision, recall, false-positive rate, false negatives, abstentions and confidence intervals. No benchmark should be presented as real-world accuracy until the validation dataset and results support that conclusion.

Do not relabel ChainScope predictions as ground truth or invent successful evaluations.

## AI explanations: constrained assistance, not forensic conclusions

AI is **optional**. Configuration defaults include `LLM_PROVIDER=ollama` and `LLM_MODEL=llama3.2:1b`, but the actual deployed model must be checked from runtime configuration/status; these defaults do **not** prove a model is active in production. Supported code paths include Groq. When the provider is unavailable, fails or returns invalid/unsupported structured claims, the service is designed to fall back to deterministic explanations.

The evidence contract requires citations for factual statements and blocks several forms of unsupported claims. This is a safeguard, **not proof of perfect factual accuracy**. Evaluating the system requires a human-reviewed dataset with claim-level support checks, unsupported-claim rate, abstention/fallback rate, latency, and a rule-only baseline. Do not let AI infer ownership, illicit intent or fraud from graph proximity.

## Security and privacy boundary

- Privileged analyst case changes require analyst authorization; signed viewer and analyst sessions exist. Review the auth implementation in `src/api/auth.py`.
- Request limiting and abuse controls are implemented in `src/api/security.py` with settings in `src/utils/config.py`. The effectiveness of these controls, especially behind proxies and under concurrency, has **not** been independently penetration-tested.
- Some blockchain read routes are intended for public use. Public on-chain data is not private, but the **selection of wallets investigated**, users' notes, and operational request logs can be sensitive. Do not assume browsing is anonymous.
- Restrict CORS to required origins, protect credentials, use HTTPS, and avoid putting access keys in documentation, client builds or screenshots.
- Don't treat an available `/docs` or health endpoint as evidence of API security.

## Single-chain and data coverage

**Current supported investigation network: Ethereum mainnet only.** The project name is aspirational; it does **not** currently mean Solana, Polygon, BNB Chain or other networks are indexed.

Data sources differ:
1. The continuously indexed PostgreSQL transaction set is **bounded and retained**, not all Ethereum history.
2. Per-wallet provider transfer queries can include categories such as external, ERC-20, internal, ERC-721 and ERC-1155 **when supported/returned by that endpoint**. Not every category is necessarily complete or indexed globally.
3. Contract execution traces, all NFT activity, off-chain ownership, attributed identities and complete historical reconstruction are **not assured**.

Use the runtime `/api/coverage` and wallet-specific coverage report for actual block range, oldest/newest timestamps, page cursors, category scope, truncation and missing records. No hardcoded block range in this README should be mistaken for current coverage.

## Accessibility and performance limitations

The 3D evidence view uses WebGL canvas, so its bubbles are not inherently screen-reader accessible. There are clickable controls, a separate wallet evidence panel, and initial reduced-motion preference support. **A complete accessible text/table alternative, keyboard-only node navigation and screen-reader/low-end-mobile conformance are not yet verified.** The graph may be slow on constrained devices. FPS caps and bounded layout/particles are optimizations, not measured throughput claims.

## Architecture

```text
Ethereum RPC / provider transfer API
         │
 ingestion / history-fetch workers ──→ PostgreSQL
         │                                │
         └─ checkpoint + provenance        ├─ stored transactions / alerts
                                          └─ case evidence / review audit
                                          │
                                  FastAPI REST endpoints
                                  │        │
                              risk rules   optional grounded AI
                                  │        │
                                  └── React dashboard / WebGL flow
```

| Layer | Technology |
|---|---|
| Network | Ethereum mainnet; Web3.py; provider RPC / transfer APIs |
| API | Python 3.12, FastAPI, asyncpg |
| Persistence | PostgreSQL |
| Analytics | Deterministic review signals and evaluation tooling |
| AI | Optional Ollama or Groq; structured grounding and fallback |
| Frontend | React, Vite, Tailwind CSS, Recharts, custom WebGL graph |
| Deployment | Railway production; Docker multi-stage frontend + API build |

### Canonical deployment

**Only the Railway `/app/` address above is the recommended frontend.** An earlier Vercel frontend URL exists as a **legacy surface**, is not guaranteed to reflect the current repository and should not be used for validation. The Railway backend root and `/docs` belong to the same service, not separate product deployments. Review and retire stale public deployment surfaces where you have control.

## Local development

Prerequisites: Python 3.12+, Node.js version compatible with current Vite, Docker Desktop, PostgreSQL CLI for manual diagnostics, plus optional Ollama.

```bash
git clone https://github.com/munavathvijay00-spec/Ai-PoweredBlockchain.git
cd Ai-PoweredBlockchain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your own values in .env; never commit .env.
docker compose up -d
# Apply repository migrations/schema relevant to your deployment
uvicorn src.api.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

**Note:** `DATABASE_URL` must point to a host reachable from the runtime. Railway internal PostgreSQL hostnames do not resolve on a local Mac. Use local Docker PostgreSQL for development or a supported secure tunnel; never publish DB credentials.

Check the corresponding setup scripts before running backfill, scoring or schema changes on a production DB. Running the API alone does not guarantee an ingestion worker is running.

## Tests and observability

```bash
# Unit and integration suite (requires appropriate dependencies/configuration)
python -m pytest tests -q

# Frontend verification
cd frontend && npm run build && npm run lint && npm run test:component
```

Read-only endpoint probe (**sequential, bounded sample; not a load test**):

```bash
python -m scripts.probe_readiness --base https://ai-poweredblockchain-production.up.railway.app --samples 5
```

A successful build or a small smoke test does **not** demonstrate production-scale reliability. Pending verification includes sustained reorg recovery, RPC outage/backoff, resource caps, load testing, security testing, keyboard access and an end-to-end case lifecycle.

## Priority roadmap (not completed work)

1. **P0 data correctness:** Repeatable canonical checkpoint/reorg tests; documented common-ancestor recovery and bounded backfill; missing-coverage alerts.
2. **P0 measurable detection:** Independent representative holdout and trustworthy precision/recall/FPR/abstention reports. Keep uncalibrated scores explicitly labeled.
3. **P0 access assurance:** Review public route threat model, session scope, rate limits, CORS and sensitive operational logs; penetration/abuse tests.
4. **P1 AI usefulness:** Claim-level human evaluation, provider comparisons, hallucination tracking, fail-closed baseline and analyst feedback.
5. **P1 workflow:** Browser E2E for authorized case creation, evidence attachment, assignments, audit history, export and integrity verification.
6. **P1 scale and access:** Large-graph performance benchmarks, accessible non-WebGL evidence representation and responsive/mobile testing.
7. **P2 deployment clarity:** Retire legacy deployment surfaces; publish audited operational runbooks. Add other chains only after Ethereum is trustworthy.

## Project context

Built as a learning-driven engineering project and evolving research prototype. Architecture and investigation features are being hardened incrementally; **enterprise-grade forensics, detection accuracy, complete chain coverage and production security certifications are not claimed**.

**Author:** Munavath Vijay · **License:** MIT
