"""On-demand grounded LLM explanations.

The endpoint is intentionally separate from ingestion so RPC/indexing throughput
never depends on an external LLM. The live AI path now uses structured claims that
must pass evidence-contract validation before any generated language is returned.
"""
import hmac
import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException

from src.agents.ai_audit import record_ai_run
from src.agents.evidence_contract import build_evidence_contract
from src.agents.explainer import evidence_explanation
from src.agents.structured_grounding import structured_explain_with_audit
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
            "evidence_url": (
                factor.get("source_url")
                or factor.get("evidence_url")
                or f"https://etherscan.io/tx/{tx_hash}"
            ),
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
    evidence_contract = build_evidence_contract(tx, factors)
    baseline = evidence_explanation(tx, factors)

    # The model must first produce structured claims; prose is rendered only after validation.
    audit = await structured_explain_with_audit(tx, factors)
    provider = str(audit.get("provider") or "disabled")
    status = str(audit.get("status") or "unknown")
    result = str(audit.get("explanation") or baseline)
    grounded_ai = bool(audit.get("ai_used") and audit.get("grounded"))

    await record_ai_run(repo.db, tx_hash=row["hash"], baseline=baseline, audit=audit)

    if grounded_ai:
        ai_explanations_total.labels(provider=provider, status="grounded").inc()
        await repo.update_explanation(row["hash"], result)
    else:
        ai_explanations_total.labels(provider=provider, status=status).inc()
        if status in {"grounding_rejected", "structured_parse_rejected"}:
            ai_grounding_rejections_total.labels(provider=provider).inc()

    warning = "Risk evidence is a review signal, not a fraud verdict."
    if status == "abstained_no_evidence":
        warning = "No supporting risk factor is stored, so ChainScope abstained instead of asking the LLM to infer one."
    elif status == "provider_not_configured":
        warning = "A real LLM provider is not configured; deterministic evidence was returned."
    elif status == "provider_no_output":
        warning = "The configured LLM did not return usable output; deterministic evidence was returned."
    elif status == "structured_parse_rejected":
        warning = "The LLM did not return the required structured evidence JSON; its output was withheld."
    elif status == "grounding_rejected":
        warning = "The LLM produced claims that failed evidence validation; its output was withheld."

    return {
        "transaction_hash": row["hash"],
        "status": "grounded_ai" if grounded_ai else "deterministic",
        "ai_status": status,
        "provider": provider,
        "model": audit.get("model") if grounded_ai else None,
        "explanation": result,
        "structured_claims": audit.get("structured_payload") if grounded_ai else None,
        "citations": _citations(row["hash"], factors),
        "evidence_contract": evidence_contract,
        "grounded": True,
        "ai_used": grounded_ai,
        "latency_ms": audit.get("latency_ms"),
        "grounding_report": audit.get("grounding_report"),
        "source_of_truth": "structured evidence contract from stored transaction facts + stored risk factors",
        "warning": warning,
    }
