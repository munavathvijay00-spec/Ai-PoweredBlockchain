"""Grounded AI enrichment batch job.

Attempts real LLM explanations for flagged transactions, records every attempt in
`ai_explanation_runs`, and persists text only when the structured grounding path
accepts the model output. Deterministic/legacy explanations do not block an upgrade.

Run: python -m scripts.explain_transactions
"""
import asyncio
import json
import time

from src.agents.ai_audit import provider_configuration, record_ai_run
from src.agents.explainer import evidence_explanation, get_explainer
from src.database.connection import close_db, get_db
from src.database.repositories import AddressRepository, TransactionRepository
from src.utils.config import get_settings


def _already_grounded_ai(value) -> bool:
    return isinstance(value, str) and value.strip().startswith("Grounded AI explanation:")


def _factors(tx):
    factors = tx.get("risk_factors") or []
    if isinstance(factors, str):
        try:
            factors = json.loads(factors)
        except (TypeError, ValueError):
            return []
    return [item for item in factors if isinstance(item, dict)] if isinstance(factors, list) else []


async def main():
    settings = get_settings()
    batch_size = max(1, min(100, int(settings.ai_enrichment_batch_size or 8)))
    min_score = max(0, min(100, int(settings.ai_enrichment_min_score or 20)))

    print("\n" + "=" * 68)
    print("🧠 CHAINSCOPE GROUNDED AI ENRICHMENT")
    print("=" * 68)

    config = provider_configuration()
    print(
        f"Provider: {config.get('provider')} | Model: {config.get('model')} | "
        f"Configured: {config.get('provider_configured')} ({config.get('configuration_reason')})"
    )
    print(f"Batch size: {batch_size} | Minimum risk score: {min_score}\n")

    started = time.time()
    db = await get_db()
    if db is None or db.pool is None:
        print("❌ Database connection failed")
        return

    addresses = AddressRepository(db)
    transactions = TransactionRepository(db, addresses)
    explainer = get_explainer()

    # Pull extra candidates because accepted AI rows may already occupy the top of
    # the risk-ranked list. We still cap actual model attempts to batch_size.
    candidates = await transactions.list_flagged(min_score=min_score, limit=min(200, batch_size * 5))

    attempts = 0
    accepted = 0
    rejected = 0
    provider_failures = 0
    no_evidence = 0
    already_grounded = 0

    for tx in candidates:
        if attempts >= batch_size:
            break
        if _already_grounded_ai(tx.get("ai_explanation")):
            already_grounded += 1
            continue

        factors = _factors(tx)
        baseline = evidence_explanation(tx, factors)
        audit = await explainer.explain_with_audit(tx, factors)
        attempts += 1

        # Every attempt is evidence: accepted, rejected, provider failure, or abstention.
        await record_ai_run(
            db,
            tx_hash=str(tx["hash"]),
            baseline=baseline,
            audit=audit,
        )

        status = str(audit.get("status") or "unknown")
        if audit.get("ai_used") and audit.get("grounded") and status == "grounded_ai":
            await transactions.update_explanation(str(tx["hash"]), str(audit["explanation"]))
            accepted += 1
            marker = "✅ accepted"
        elif status == "grounding_rejected":
            rejected += 1
            marker = "🛡️ rejected"
        elif status == "abstained_no_evidence":
            no_evidence += 1
            marker = "⏭️ no evidence"
        else:
            provider_failures += 1
            marker = f"⚠️ {status}"

        print(
            f"{marker:24} {str(tx['hash'])[:18]}… "
            f"score={int(tx.get('risk_score') or 0):3d} latency={int(audit.get('latency_ms') or 0)}ms"
        )

    elapsed = time.time() - started
    print("\n" + "=" * 68)
    print(f"Model attempts:           {attempts}")
    print(f"Accepted grounded AI:     {accepted}")
    print(f"Grounding rejections:     {rejected}")
    print(f"Provider/no-output:       {provider_failures}")
    print(f"Abstained (no evidence):  {no_evidence}")
    print(f"Already grounded AI:      {already_grounded}")
    print(f"Elapsed:                  {elapsed:.1f}s")
    print("=" * 68 + "\n")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
