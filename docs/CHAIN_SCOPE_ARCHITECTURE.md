# ChainScope: executable architecture and gaps (2026-10-12)

## Repository assessment
Existing application: React/Vite frontend, FastAPI backend, Python Ethereum RPC ingestion worker, PostgreSQL on Railway, Vercel frontend. On-demand receipt log decoding supports several ERC token events and Uniswap V2 swaps. Risk evidence v2 is explicitly uncalibrated. Read-only wallet summaries are bounded to retained transactions.

**Blocking issue:** ingestion currently deletes transactions older than 30 minutes. The worker starts at the chain tip on first boot, and an increasing block cursor is not proof of contiguous canonical history or reorg safety. Do not market this dataset as complete Ethereum history.

## Reliable target architecture
1. Provider adapter with explicit capability discovery, chain-ID validation, timeout, retry/backoff, and rate-limit reporting.
2. Canonical block index storing chain ID, block number, block hash, parent hash, ingestion status, and confirmations; detect parent mismatch, roll back/replay orphaned data.
3. Separate durable raw ingestion from bounded asynchronous enrichment of receipts, logs, metadata, and traces. Idempotent composite keys include chain/block context and log index.
4. Address-indexed native and token movement tables with cursor pagination, provider provenance, and exact integer quantities. Maintain bounded materialized aggregates for common queries.
5. Investigation API returns source-linked evidence and coverage windows, not unqualified all-time wallet counts.
6. Risk rules produce rule/version/window/baseline/evidence references; evaluated against independent labeled cases. LLM is optional and may only summarize validated evidence.
7. Graph queries use capped depth, nodes, edges, and time windows; edges represent observed movement rather than proven ultimate ownership.

## Data-provider capability matrix

| Source | Standard native blocks/receipts | Address-wide historical transfers | Internal traces | Historical token events |
|---|---|---|---|---|
| Standard Ethereum JSON-RPC | Yes, with provider retention limits | No general address index | Not guaranteed | eth_getLogs subject to provider limits |
| Indexed explorer API | Provider-dependent | Often, subject to key and pagination | Provider-dependent | Often, subject to key and pagination |
| Trace-capable archival RPC | Yes | Still requires indexing | Trace/debug methods if enabled | Logs if supported |
| Current platform database | Recent retained subset only | Recent retained subset only | No | No persistent token event index |

Never silently treat an unsupported provider capability as an empty history.

## Initial API specification
- GET /api/coverage: explicit observed bounds, capabilities, and limitations.
- GET /api/wallets/{address}?limit=50: bounded recent retained native transfers with cited counterparties.
- GET /api/transactions/{hash}: stored native transaction and risk evidence assessment.
- GET /api/transactions/{hash}/events: on-demand receipt event decoding.
- Future GET /api/investigations/{id}/graph?depth=1: bounded, persisted, provenance-aware graph.
- Future POST /api/investigations: asynchronous indexed investigation job.

## Database design
Introduce migrations for canonical_blocks(chain_id, number, hash, parent_hash, status), raw_receipts(chain_id, tx_hash, block_hash), token_events(chain_id, block_hash, tx_hash, log_index, token_contract, event_type, raw_amount), traces(chain_id, block_hash, tx_hash, trace_address), provider_requests(provider, capability, status, requested_at), and coverage_ranges(chain_id, source, from_block, to_block, completeness). Unique keys must include chain context; raw monetary amounts must use numeric/integer/text exact representations.

Do not add large tables to the current 500 MB Railway volume until physical capacity is increased and retention policy is redesigned.

## Milestones and verification
1. Expose truthful coverage, fix misleading amount-based risk labels, establish CI (partially implemented).
2. Expand volume and backup strategy; introduce migrations and canonical reorg-aware block index.
3. Persist receipts/token events with independent explorer cross-checks and source metadata.
4. Implement address-indexed history and bounded fund-flow graph; verify against real addresses.
5. Add behavioral rule evidence and real labeled evaluation, no fabricated accuracy.
6. Implement evidence-grounded reports, premium UI, end-to-end tests, load tests, security review, and deployment checks.

## Critical technical risks
- Short data retention and limited storage prevent historical investigation.
- Standard RPC cannot retrieve complete arbitrary wallet history without an index.
- Missing canonical block hashes and rollback expose analyses to reorg errors.
- Untrusted token metadata and AI output require validation and escaping.
- Risk scores are historical heuristic priorities, not probabilities.
- Mocked unit tests cannot prove correctness against mainnet.
