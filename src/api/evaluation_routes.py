"""Independent-label evaluation endpoints.

A metric is published only after explicit external labels exist. Product risk
scores are never used as ground truth for their own evaluation.
"""
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.api.dependencies import get_transaction_repo
from src.database.repositories import TransactionRepository
from src.metrics import (
    risk_benchmark_precision,
    risk_benchmark_recall,
    risk_benchmark_coverage,
    risk_benchmark_sample_size,
)
from src.risk.evaluation import evaluate_predictions
from src.risk.evidence_v2 import assess_evidence
from src.utils.config import get_settings

router = APIRouter(prefix="/api/evaluation", tags=["detection evaluation"])


async def require_evaluation_key(x_api_key: str | None = Header(default=None)):
    expected = get_settings().api_key
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")


async def _require_schema(repo: TransactionRepository):
    exists = await repo.db.fetchval("SELECT to_regclass('detection_evaluations') IS NOT NULL")
    if not exists:
        raise HTTPException(
            status_code=503,
            detail="Detection evaluation schema not initialized; apply scripts/intelligence_v2.sql",
        )


def _decode_factors(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


def _publish(metrics):
    risk_benchmark_sample_size.set(metrics["sample_size"])
    if metrics.get("precision") is not None:
        risk_benchmark_precision.set(metrics["precision"])
    if metrics.get("recall") is not None:
        risk_benchmark_recall.set(metrics["recall"])
    if metrics.get("decision_coverage") is not None:
        risk_benchmark_coverage.set(metrics["decision_coverage"])


@router.get("/latest")
async def latest_evaluation(repo: TransactionRepository = Depends(get_transaction_repo)):
    try:
        await _require_schema(repo)
    except HTTPException:
        return {
            "measured": False,
            "reason": "evaluation_schema_not_initialized",
            "warning": "No detection accuracy claim is available.",
        }
    row = await repo.db.fetchrow(
        """SELECT id,evaluator_version,threshold,sample_size,metrics,label_sources,created_at
           FROM detection_evaluations ORDER BY created_at DESC LIMIT 1"""
    )
    if not row:
        return {
            "measured": False,
            "reason": "no_independent_evaluation_run",
            "warning": "Precision and recall remain unmeasured until independently labelled cases are evaluated.",
        }
    metrics = row.get("metrics") or {}
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    _publish(metrics)
    return {
        "measured": True,
        "evaluation_id": row["id"],
        "evaluator_version": row["evaluator_version"],
        "threshold": row["threshold"],
        "sample_size": row["sample_size"],
        "metrics": metrics,
        "label_sources": row.get("label_sources"),
        "created_at": row["created_at"],
        "warning": "Metrics describe only the labelled validation set and are not calibrated fraud probabilities.",
    }


@router.post("/run", dependencies=[Depends(require_evaluation_key)])
async def run_evaluation(
    threshold: int = Query(20, ge=0, le=100),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _require_schema(repo)
    rows = await repo.db.fetch(
        """
        SELECT dl.id, dl.tx_hash, dl.label, dl.label_source, dl.label_reference,
               t.risk_score, t.risk_factors
        FROM detection_labels dl
        LEFT JOIN transactions t ON t.hash = dl.tx_hash
        ORDER BY dl.id
        """
    )
    if not rows:
        raise HTTPException(status_code=409, detail="No independent detection labels are stored")

    cases = []
    missing_product_evidence = 0
    sources = set()
    for row in rows:
        sources.add(row["label_source"])
        if row.get("risk_score") is None:
            prediction = "abstain"
            missing_product_evidence += 1
        else:
            factors = _decode_factors(row.get("risk_factors"))
            assessment = assess_evidence(factors, row["tx_hash"])
            if assessment.get("assessment") == "insufficient_evidence":
                prediction = "abstain"
            else:
                prediction = "1" if int(row["risk_score"]) >= threshold else "0"
        cases.append({
            "case_id": str(row["id"]),
            "label": int(row["label"]),
            "prediction": prediction,
        })

    metrics = evaluate_predictions(cases)
    metrics["missing_product_evidence"] = missing_product_evidence
    metrics["threshold"] = threshold
    evaluation_id = await repo.db.fetchval(
        """
        INSERT INTO detection_evaluations (
            evaluator_version, threshold, sample_size, metrics, label_sources
        ) VALUES ('chainscope-eval-v2',$1,$2,$3::jsonb,$4::jsonb)
        RETURNING id
        """,
        threshold,
        metrics["sample_size"],
        json.dumps(metrics),
        json.dumps(sorted(sources)),
    )
    _publish(metrics)
    return {
        "measured": True,
        "evaluation_id": evaluation_id,
        "metrics": metrics,
        "label_sources": sorted(sources),
        "warning": "Use only independently established labels; never label from ChainScope's own risk score.",
    }
