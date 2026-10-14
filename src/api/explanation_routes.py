"""On-demand grounded LLM explanations.

The endpoint is intentionally separate from ingestion so RPC/indexing throughput
never depends on an external LLM. Every accepted AI sentence is bounded by the
stored transaction facts and [E#] evidence references.
"""
import hmac
import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException

from src.agents.explainer import get_explainer, evidence_explanation
from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.metrics import ai_explanations_total, ai_grounding_rejections_total
from src.utils.config import get_settings

router = APIRouter(prefix="/api/transactions", tags=["grounded explanations"])
TX_HASH = re.compile(r"^0x[a-fA-F0-9]{64}$")


async def require_explanation_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


def _factors(row):
    factors = row.get("risk_factors") or []
    if isinstance(factors, str):
        try:
            factors = json.loads(factors)
        except (TypeError, ValueError):
            return []
    return [factor for factor in factors if isinstance(factor, dict)] if isinstance(factors, list) else []


def _citations(tx_hash: str, factors: list[dict]) -> list[dict]:
    citations = []
    for index, factor in enumerate(factors, start=1):
        citations.append({
            "id": f"E{index}",
            "factor": factor.get("factor"),
            "reason": factor.get("reason") or "Recorded scoring signal",
            "points": factor.get("points"),
            "source": factor.get("source") or "chainscope-risk-engine",
            "evidence_url": factor.get("evidence_url") or f"https://etherscan.io/tx/{tx_hash}",
        })
    return citations


@router.post("/{tx_hash}/explain", dependencies=[Depends(require_explanation_key)])
async def explain_transaction(
    tx_hash: str,
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    if not TX_HASH.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail="Invalid Ethereum transaction hash")
    row = await repo.get_by_hash(tx_hash.lower())
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found in retained ChainScope evidence")

    factors = _factors(row)
    tx = {
        "hash": row["hash"],
        "from_address": row["from_address"],
        "to_address": row["to_address"],
        "value": row["value"],
        "value_wei": row["value"],
        "block_number": row["block_number"],
        "risk_score": row.get("risk_score", 0),
    }
    baseline = evidence_explanation(tx, factors)
    settings = get_settings()
    provider = (settings.llm_provider or "disabled").lower()

    # No evidence -> no AI call. This is an explicit abstention, not a benign verdict.
    if not factors:
        ai_explanations_total.labels(provider=provider, status="abstained_no_evidence").inc()
        return {
            "transaction_hash": row["hash"],
            "status": "deterministic",
            "provider": provider,
            "explanation": baseline,
            "citations": [],
            "grounded": True,
            "ai_used": False,
            "warning": "No supporting risk factor is stored, so ChainScope did not ask an LLM to infer one.",
        }

    result = await get_explainer().explain(tx, factors)
    grounded_ai = result.startswith("Grounded AI explanation:")
    if grounded_ai:
        ai_explanations_total.labels(provider=provider, status="grounded").inc()
        await repo.update_explanation(row["hash"], result)
    else:
        # explain() returns the deterministic baseline whenever provider access fails
        # or grounding validation rejects the model output.
        ai_explanations_total.labels(provider=provider, status="deterministic_fallback").inc()
        if provider in {"groq", "ollama"}:
            ai_grounding_rejections_total.labels(provider=provider).inc()

    return {
        "transaction_hash": row["hash"],
        "status": "grounded_ai" if grounded_ai else "deterministic",
        "provider": provider,
        "model": settings.llm_model if grounded_ai else None,
        "explanation": result,
        "citations": _citations(row["hash"], factors),
        "grounded": True,
        "ai_used": grounded_ai,
        "source_of_truth": "stored transaction facts + stored risk factors",
        "warning": "Risk evidence is a review signal, not a fraud verdict.",
    }
