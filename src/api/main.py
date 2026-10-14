"""FastAPI application entry point."""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
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
from src.api.historical_routes import router as historical_router
from src.api.entity_routes import router as entity_router
from src.api.evaluation_routes import router as evaluation_router
from src.api.models import HealthResponse
from src.database.connection import get_db, close_db
from src.metrics import api_requests_total, api_request_duration_seconds, db_health_up
from src.risk.ofac_intelligence import refresh_ofac
from src.utils.config import get_settings


async def _refresh_verified_intelligence(db):
    """Best-effort official-source refresh that never blocks API readiness."""
    try:
        count = await asyncio.wait_for(refresh_ofac(db), timeout=45)
        if count:
            logger.info("Verified intelligence refresh completed: {} OFAC Ethereum addresses", count)
        else:
            logger.warning("Verified intelligence refresh returned no new rows; last-known-good snapshot preserved")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Verified intelligence background refresh unavailable; preserving last-known-good snapshot: {}",
            type(exc).__name__,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Blockchain Intelligence API")
    db = await get_db()
    db_health_up.set(1)
    intelligence_task = asyncio.create_task(_refresh_verified_intelligence(db))
    logger.success("API ready")
    try:
        yield
    finally:
        logger.info("Shutting down")
        if not intelligence_task.done():
            intelligence_task.cancel()
            try:
                await intelligence_task
            except asyncio.CancelledError:
                pass
        await close_db()


app = FastAPI(
    title="Blockchain Intelligence API",
    description="Evidence-grounded Ethereum intelligence",
    version="1.1.0",
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
app.include_router(historical_router)
app.include_router(entity_router)
app.include_router(evaluation_router)


@app.get("/", response_model=HealthResponse, tags=["health"])
async def root():
    settings = get_settings()
    return HealthResponse(
        status="operational",
        service="Blockchain Intelligence Platform",
        version="1.1.0",
        database=settings.postgres_db,
        blockchain="ethereum-mainnet",
    )


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
