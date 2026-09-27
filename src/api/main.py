"""
FastAPI application entry point.
Run with: uvicorn src.api.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import router
from src.api.models import HealthResponse
from src.database.connection import get_db, close_db
from src.utils.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("🚀 Starting Blockchain Intelligence API...")
    await get_db()
    logger.success("✅ API ready")
    yield
    logger.info("🔌 Shutting down...")
    await close_db()


app = FastAPI(
    title="Blockchain Intelligence API",
    description="AI-powered Ethereum transaction analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow browser requests from any origin (including Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API routes
app.include_router(router)


@app.get("/", response_model=HealthResponse, tags=["health"])
async def root():
    """Health check and API info."""
    settings = get_settings()
    return HealthResponse(
        status="operational",
        service="Blockchain Intelligence Platform",
        version="1.0.0",
        database=settings.postgres_db,
        blockchain="ethereum-mainnet",
    )