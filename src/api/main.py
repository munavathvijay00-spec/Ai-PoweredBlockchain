"""FastAPI application entry point."""
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_client import generate_latest, REGISTRY

from src.api.routes import router
from src.api.agent_routes import router as agent_router
from src.api.event_routes import router as event_router
from src.api.wallet_routes import router as wallet_router
from src.api.coverage_routes import router as coverage_router
from src.api.graph_routes import router as graph_router
from src.api.indexed_transfer_routes import router as indexed_transfer_router
from src.api.observability_routes import router as observability_router
from src.api.explanation_routes import router as explanation_router
from src.api.ai_routes import router as ai_router
from src.api.historical_routes import router as historical_router
from src.api.entity_routes import router as entity_router
from src.api.evaluation_routes import router as evaluation_router
from src.api.ml_routes import router as ml_router
from src.api.models import HealthResponse
from src.agents.ai_audit import ensure_ai_audit_schema
from src.database.connection import get_db, close_db
from src.metrics import api_requests_total, api_request_duration_seconds, db_health_up
from src.ml.model_registry import model_status as independent_ml_status, train_and_register
from src.risk.external_benchmark import external_benchmark_summary, sync_external_benchmark
from src.risk.ofac_intelligence import refresh_ofac
from src.risk.official_entities import sync_official_entities
from src.utils.config import get_settings

TARGET_EXTERNAL_BENCHMARK = 500
FRONTEND_DIST = Path("/app/frontend_dist")


async def _refresh_verified_intelligence(db):
    """Best-effort official-source refresh that never blocks API readiness."""
    try:
        official_count = await sync_official_entities(db)
        if official_count:
            logger.info("Verified entity refresh completed: {} first-party protocol addresses", official_count)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("First-party entity registry refresh unavailable; preserving stored rows: {}", type(exc).__name__)

    try:
        count = await asyncio.wait_for(refresh_ofac(db), timeout=45)
        if count:
            logger.info("Verified intelligence refresh completed: {} OFAC Ethereum addresses", count)
        else:
            logger.warning("Verified intelligence refresh returned no new OFAC rows; last-known-good snapshot preserved")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Verified OFAC background refresh unavailable; preserving last-known-good snapshot: {}", type(exc).__name__)


async def _prepare_ai_and_benchmark(db):
    """Create audit storage and grow the independent benchmark toward evaluation scale."""
    try:
        await ensure_ai_audit_schema(db)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("AI audit schema unavailable: {}", type(exc).__name__)

    try:
        summary = await external_benchmark_summary(db)
        if summary.get("sample_size", 0) < TARGET_EXTERNAL_BENCHMARK:
            result = await asyncio.wait_for(
                sync_external_benchmark(db, per_class=TARGET_EXTERNAL_BENCHMARK // 2),
                timeout=90,
            )
            logger.info(
                "External detection benchmark refreshed: {} rows from {} (target={})",
                result.get("rows_fetched", 0), result.get("source"), TARGET_EXTERNAL_BENCHMARK,
            )
        else:
            logger.info("External detection benchmark already present: {} cases", summary.get("sample_size"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("External benchmark background sync unavailable; API remains operational: {}", type(exc).__name__)


async def _prepare_independent_ml():
    """Train/refresh a provenance-gated, runtime-compatible shadow model."""
    try:
        db = await get_db()
        benchmark = await external_benchmark_summary(db)
        for _ in range(10):
            if benchmark.get("sample_size", 0) >= TARGET_EXTERNAL_BENCHMARK:
                break
            await asyncio.sleep(5)
            benchmark = await external_benchmark_summary(db)

        status = await independent_ml_status()
        model_rows = int(status.get("dataset_rows") or 0) if status.get("available") else 0
        benchmark_rows = int(benchmark.get("sample_size") or 0)
        runtime_compatible = bool(status.get("runtime_compatible"))

        if status.get("available") and runtime_compatible and model_rows >= benchmark_rows:
            test = status.get("test_metrics") or {}
            logger.info(
                "Independent ML model current: family={} mode={} rows={} gate={} test_auc={} test_f1={} test_precision={} test_brier={}",
                status.get("model_family"), status.get("deployment_mode"), model_rows,
                status.get("production_quality_gate_passed"), test.get("roc_auc"), test.get("f1"),
                test.get("precision"), test.get("brier"),
            )
            return

        if status.get("available") and not runtime_compatible:
            logger.info(
                "Independent ML model migration required: stored_family={} expected_family={}",
                status.get("model_family"), status.get("expected_model_family"),
            )

        if benchmark_rows < 100:
            logger.warning("Independent ML bootstrap deferred: only {} external cases available", benchmark_rows)
            return

        metadata = await asyncio.wait_for(
            train_and_register(limit=max(benchmark_rows, 500)),
            timeout=120,
        )
        logger.info(
            "Independent ML model registered/refreshed: family={} rows={} AUC={} F1={} precision={} brier={} mode={} gate={}",
            metadata.get("model_family"), metadata.get("dataset_rows"),
            (metadata.get("test_metrics") or {}).get("roc_auc"),
            (metadata.get("test_metrics") or {}).get("f1"),
            (metadata.get("test_metrics") or {}).get("precision"),
            (metadata.get("test_metrics") or {}).get("brier"),
            metadata.get("deployment_mode"), metadata.get("production_quality_gate_passed"),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Independent ML bootstrap unavailable; production rule scoring remains unchanged: {}", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Blockchain Intelligence API")
    db = await get_db()
    db_health_up.set(1)
    background_tasks = [
        asyncio.create_task(_refresh_verified_intelligence(db)),
        asyncio.create_task(_prepare_ai_and_benchmark(db)),
        asyncio.create_task(_prepare_independent_ml()),
    ]
    logger.success("API ready")
    try:
        yield
    finally:
        logger.info("Shutting down")
        for task in background_tasks:
            if not task.done():
                task.cancel()
        for task in background_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        await close_db()


app = FastAPI(
    title="Blockchain Intelligence API",
    description="Evidence-grounded Ethereum intelligence",
    version="1.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observe_http(request: Request, call_next):
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_label = getattr(route, "path", None) or "unmatched"
        method = request.method
        api_requests_total.labels(method=method, route=route_label, status=str(status)).inc()
        api_request_duration_seconds.labels(method=method, route=route_label).observe(time.monotonic() - start)


app.include_router(router)
app.include_router(agent_router)
app.include_router(event_router)
app.include_router(wallet_router)
app.include_router(coverage_router)
app.include_router(graph_router)
app.include_router(indexed_transfer_router)
app.include_router(observability_router)
app.include_router(explanation_router)
app.include_router(ai_router)
app.include_router(historical_router)
app.include_router(entity_router)
app.include_router(evaluation_router)
app.include_router(ml_router)


@app.get("/", response_model=HealthResponse, tags=["health"])
async def root():
    settings = get_settings()
    return HealthResponse(
        status="operational",
        service="Blockchain Intelligence Platform",
        version="1.5.0",
        database=settings.postgres_db,
        blockchain="ethereum-mainnet",
    )


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


if FRONTEND_DIST.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="chainscope_frontend")
    logger.info("Bundled ChainScope frontend mounted at /app")
else:
    logger.warning("Bundled ChainScope frontend not found; API-only mode")
