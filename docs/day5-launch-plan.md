# Day 5: real intelligence, multi-agent deployment and launch gates

## What is actually deployed

- **Chain ingestion:** Ethereum mainnet through Web3/Alchemy. A dedicated Railway worker runs `python -m src.ingest.loop` and restores the durable PostgreSQL `ingest_cursor` checkpoint. Up to three sequential blocks are processed per 15-second iteration. Lag is logged, not silently skipped.
- **Risk intelligence:** The official U.S. Treasury OFAC SDN CSV is downloaded and ETH-tagged addresses are parsed, validated and persisted to `verified_address_intelligence` with source, entity ID, name and timestamp. Refreshes run on startup and daily. A failed/empty/suspiciously shrunken feed preserves the previous snapshot. Manual blacklist records are separate; AI never invents sanctioned addresses.
- **Risk processing:** Deterministic scoring and sanctions/direct-exposure checks precede natural-language explanations. The Groq explainer is optional and has a fallback. Explanations are *not* evidence that an address is sanctioned.
- **Multi-agent analysis:** `src/agents/orchestrator.py` routes user queries to chain, account, transaction and pattern agents. These run inside the existing application, not as four independently deployed cloud services. Do not claim distributed agent infrastructure without a separate deployment.
- **Storage:** Railway PostgreSQL has a 500 MB persistent volume. SQL `pg_database_size` is a **logical** size proxy; the Railway `DISK_USAGE_GB` metric is the authoritative physical disk signal.

## Architecture

```text
Ethereum mainnet / Alchemy
            |
            v
Railway ingestion worker -----> OFAC SDN official feed
  checkpoint + scoring         verified source metadata
            |
            v
      Railway PostgreSQL <---- FastAPI (Railway)
                                   |
                            React UI (Vercel)
                                   |
                         multi-agent query router
                      chain/account/tx/pattern agents
```

## Non-negotiable physical disk gate

**Launch requires physical disk strictly below 80%, ideally below 70% with room for WAL spikes.** With a 500 MB volume, 80% is 400 MB. Do not confuse `pg_database_size` (~147 MB at the last verified run) with physical volume usage (~401 MB at the last check). Railway metrics may use GB units; check the volume size and metric unit convention before comparing.

At or above 75%: alert and inspect Railway volume metrics, PostgreSQL WAL retention/replication slots, and table/index growth. At or above 80%: **do not certify launch**. Safest capacity response is to **expand the existing volume** in Railway's dashboard (e.g. 1 GB or larger), after confirming Railway's current volume-resize procedure and backups; then recheck metrics. The current connector does not expose volume resizing. Do **not** detach/replace/delete the existing volume, manually delete WAL, or run `VACUUM FULL` under disk pressure. Ordinary PostgreSQL autovacuum and bounded retention may continue; do not assume they immediately reduce the physical volume metric.

## Day 5 Part 1: multi-agent cloud deployment verification

- [x] Existing API and worker deployed to Railway from GitHub `main`.
- [x] Worker startup command corrected; ingestion checkpoint, OFAC sync, scoring and live block processing observed.
- [x] Agent orchestration implementation exists in repository.
- [ ] Verify the cloud API exposes and authenticates the intended multi-agent query workflow; do not equate a module existing with an accessible endpoint.
- [ ] Exercise chain/account/transaction/pattern routes, timeout and provider-failure fallbacks.
- [ ] Check the worker is closing the observed chain-head lag.
- [ ] Meet the physical disk gate (<80%).

## Day 5 Part 2: polish and launch checklist

- [ ] Validate nonzero-offset pagination using live HTTP requests and distinct returned hashes.
- [ ] Verify flagged totals and dashboard stats against SQL counts (not capped lists).
- [ ] Confirm live OFAC source attribution, refresh timestamp and safe fallback behavior.
- [ ] Confirm production CORS, rate limits, errors, secrets and health checks.
- [ ] Validate Vercel UI on mobile and desktop without unnecessary redesign.
- [ ] Capture API/worker deployment SHA, CI status, database volume utilization and a short smoke-test log before announcing launch.

**Scope note:** This document distinguishes verified production functionality from incomplete launch gates. It is not a launch certificate.
