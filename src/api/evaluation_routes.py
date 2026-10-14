"""Independent-label evaluation endpoints.

A metric is published only after explicit external labels exist. Product risk
scores are never used as ground truth for their own evaluation, and labels that
reuse the same source as a scoring factor are excluded as source leakage.
"""
import hmac
import json
import re
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

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
from src.risk.external_benchmark import (
    evaluate_external_benchmark,
    external_benchmark_summary,
    sync_external_benchmark,
)
from src.risk.scorer import get_scorer
from src.utils.config import get_settings

router = APIRouter(prefix="/api/evaluation", tags=["detection evaluation"])
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
_SELF_LABEL_SOURCES = {
    "chainscope",
    "chainscope-risk",
    "chainscope-risk-score",
    "risk-score",
    "model-output",
}
MIN_PUBLISHABLE_CASES = 30
MIN_PUBLISHABLE_CLASS_SUPPORT = 10


class DetectionLabelInput(BaseModel):
    tx_hash: str
    label: int = Field(ge=0, le=1)
    label_source: str = Field(min_length=2, max_length=120)
    label_reference: str = Field(min_length=2, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)


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


def _publication_gate(metrics):
    reasons = []
    sample_size = int(metrics.get("sample_size") or 0)
    positive_support = int(metrics.get("positive_support") or 0)
    negative_support = int(metrics.get("negative_support") or 0)
    if sample_size < MIN_PUBLISHABLE_CASES:
        reasons.append(f"sample_size_below_{MIN_PUBLISHABLE_CASES}")
    if positive_support < MIN_PUBLISHABLE_CLASS_SUPPORT:
        reasons.append(f"positive_support_below_{MIN_PUBLISHABLE_CLASS_SUPPORT}")
    if negative_support < MIN_PUBLISHABLE_CLASS_SUPPORT:
        reasons.append(f"negative_support_below_{MIN_PUBLISHABLE_CLASS_SUPPORT}")
    return {
        "publishable": not reasons,
        "reasons": reasons,
        "minimum_sample_size": MIN_PUBLISHABLE_CASES,
        "minimum_class_support": MIN_PUBLISHABLE_CLASS_SUPPORT,
    }


def _publish(metrics):
    gate = metrics.get("publication_gate") or _publication_gate(metrics)
    if not gate.get("publishable"):
        return
    risk_benchmark_sample_size.set(metrics["sample_size"])
    if metrics.get("precision") is not None:
        risk_benchmark_precision.set(metrics["precision"])
    if metrics.get("recall") is not None:
        risk_benchmark_recall.set(metrics["recall"])
    if metrics.get("decision_coverage") is not None:
        risk_benchmark_coverage.set(metrics["decision_coverage"])


def _normalize_label(item: DetectionLabelInput):
    if not TX_HASH.fullmatch(item.tx_hash):
        raise HTTPException(status_code=422, detail=f"Invalid transaction hash: {item.tx_hash}")
    source = item.label_source.strip()
    reference = item.label_reference.strip()
    source_key = source.lower()
    if source_key in _SELF_LABEL_SOURCES or "chainscope" in source_key:
        raise HTTPException(
            status_code=422,
            detail="Detection labels must come from an independent source, not ChainScope output",
        )
    if reference.lower().startswith("chainscope:"):
        raise HTTPException(
            status_code=422,
            detail="label_reference must identify independent evidence",
        )
    return item.tx_hash.lower(), int(item.label), source, reference, item.notes


def _source_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _host(value: object) -> str:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return ""
    return (parsed.hostname or "").lower().removeprefix("www.")


def _case_has_source_leakage(label_rows, factors) -> bool:
    """Detect obvious evaluation leakage when a label and a scoring factor cite the same source."""
    factor_sources = {_source_key(f.get("source")) for f in factors if f.get("source")}
    factor_sources.discard("")
    factor_hosts = {
        _host(f.get("source_url") or f.get("evidence_url"))
        for f in factors
        if f.get("source_url") or f.get("evidence_url")
    }
    factor_hosts.discard("")

    for row in label_rows:
        label_source = _source_key(row.get("label_source"))
        if label_source:
            for factor_source in factor_sources:
                if len(label_source) >= 6 and len(factor_source) >= 6 and (
                    label_source in factor_source or factor_source in label_source
                ):
                    return True
        reference_host = _host(row.get("label_reference"))
        if reference_host and reference_host in factor_hosts:
            return True
    return False


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
    gate = metrics.get("publication_gate") or _publication_gate(metrics)
    metrics["publication_gate"] = gate
    _publish(metrics)
    return {
        "measured": True,
        "publishable": bool(gate.get("publishable")),
        "evaluation_id": row["id"],
        "evaluator_version": row["evaluator_version"],
        "threshold": row["threshold"],
        "sample_size": row["sample_size"],
        "metrics": metrics,
        "label_sources": row.get("label_sources"),
        "created_at": row["created_at"],
        "warning": "Metrics describe only the leakage-audited labelled validation set and are not calibrated fraud probabilities.",
    }


@router.get("/labels/summary")
async def label_summary(repo: TransactionRepository = Depends(get_transaction_repo)):
    await _require_schema(repo)
    rows = await repo.db.fetch(
        """
        SELECT label_source, COUNT(*) AS rows, COUNT(DISTINCT tx_hash) AS unique_transactions,
               MIN(labelled_at) AS oldest_labelled_at, MAX(labelled_at) AS newest_labelled_at
        FROM detection_labels
        GROUP BY label_source
        ORDER BY label_source
        """
    )
    total_rows = sum(int(row["rows"]) for row in rows)
    unique_transactions = int(await repo.db.fetchval(
        "SELECT COUNT(DISTINCT tx_hash) FROM detection_labels"
    ) or 0)
    return {
        "label_rows": total_rows,
        "unique_transactions": unique_transactions,
        "sources": rows,
        "ready_for_evaluation": unique_transactions > 0,
        "ready_for_publishable_metrics": unique_transactions >= MIN_PUBLISHABLE_CASES,
        "minimum_publishable_cases": MIN_PUBLISHABLE_CASES,
        "warning": "Labels must be independently established; ChainScope scores are not ground truth.",
    }


@router.post("/labels/import", dependencies=[Depends(require_evaluation_key)])
async def import_labels(
    items: list[DetectionLabelInput],
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    await _require_schema(repo)
    if not items or len(items) > 500:
        raise HTTPException(status_code=422, detail="Provide 1-500 independent labels")

    normalized = [_normalize_label(item) for item in items]
    inserted = 0
    async with repo.db.transaction():
        for tx_hash, label, source, reference, notes in normalized:
            row_id = await repo.db.fetchval(
                """
                INSERT INTO detection_labels (
                    tx_hash, label, label_source, label_reference, notes
                ) VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (tx_hash, label_source, label_reference) DO NOTHING
                RETURNING id
                """,
                tx_hash, label, source, reference, notes,
            )
            if row_id is not None:
                inserted += 1

    return {
        "submitted": len(normalized),
        "inserted": inserted,
        "duplicates_ignored": len(normalized) - inserted,
        "policy": "independent labels only; ChainScope output cannot label itself",
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

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["tx_hash"]].append(row)

    conflicts = [
        tx_hash for tx_hash, tx_rows in grouped.items()
        if len({int(row["label"]) for row in tx_rows}) > 1
    ]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conflicting independent labels exist for {len(conflicts)} transaction(s); "
                "resolve label provenance before publishing metrics"
            ),
        )

    cases = []
    missing_product_evidence = 0
    excluded_source_leakage = 0
    leakage_examples = []
    sources = set()
    for tx_hash, tx_rows in grouped.items():
        representative = tx_rows[0]
        factors = _decode_factors(representative.get("risk_factors"))
        if _case_has_source_leakage(tx_rows, factors):
            excluded_source_leakage += 1
            if len(leakage_examples) < 5:
                leakage_examples.append(tx_hash)
            continue

        sources.update(row["label_source"] for row in tx_rows)
        if representative.get("risk_score") is None:
            prediction = "abstain"
            missing_product_evidence += 1
        else:
            assessment = assess_evidence(factors, tx_hash)
            if assessment.get("assessment") == "insufficient_evidence":
                prediction = "abstain"
            else:
                prediction = "1" if int(representative["risk_score"]) >= threshold else "0"
        cases.append({
            "case_id": tx_hash,
            "label": int(representative["label"]),
            "prediction": prediction,
        })

    if not cases:
        raise HTTPException(
            status_code=409,
            detail="No leakage-free labelled cases remain for evaluation",
        )

    metrics = evaluate_predictions(cases)
    metrics["missing_product_evidence"] = missing_product_evidence
    metrics["excluded_source_leakage"] = excluded_source_leakage
    metrics["source_leakage_examples"] = leakage_examples
    metrics["threshold"] = threshold
    metrics["raw_label_rows"] = len(rows)
    metrics["unique_labeled_transactions"] = len(grouped)
    metrics["leakage_free_transactions"] = len(cases)
    metrics["publication_gate"] = _publication_gate(metrics)
    evaluation_id = await repo.db.fetchval(
        """
        INSERT INTO detection_evaluations (
            evaluator_version, threshold, sample_size, metrics, label_sources
        ) VALUES ('chainscope-eval-v4',$1,$2,$3::jsonb,$4::jsonb)
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
        "publishable": metrics["publication_gate"]["publishable"],
        "evaluation_id": evaluation_id,
        "metrics": metrics,
        "label_sources": sorted(sources),
        "warning": "Use only independently established, source-separated labels; never label from ChainScope's own risk score.",
    }


@router.get("/external")
async def external_evaluation(
    threshold: int = Query(20, ge=0, le=100),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Run the current transaction-native scorer against the synced external smoke benchmark."""
    summary = await external_benchmark_summary(repo.db)
    if not summary["sample_size"]:
        return {
            **summary,
            "measured": False,
            "reason": "external_benchmark_not_synced",
        }
    result = await evaluate_external_benchmark(repo.db, get_scorer(), threshold=threshold)
    result["benchmark_summary"] = summary
    return result


@router.post("/external/refresh", dependencies=[Depends(require_evaluation_key)])
async def refresh_external_evaluation(
    per_class: int = Query(100, ge=1, le=100),
    repo: TransactionRepository = Depends(get_transaction_repo),
):
    """Refresh the external public smoke benchmark without importing its labels into scoring."""
    result = await sync_external_benchmark(repo.db, per_class=per_class)
    result["benchmark_summary"] = await external_benchmark_summary(repo.db)
    return result
