"""
Prometheus metrics for the blockchain intelligence platform.

All metrics are module-level singletons — Prometheus client handles
the global registry automatically. Importing this module is enough.
"""
import time
from contextlib import contextmanager
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from typing import Optional


# ==============================================================
# INGEST METRICS
# ==============================================================

ingest_blocks_total = Counter(
    "ingest_blocks_total",
    "Total number of blocks successfully ingested",
)

ingest_transactions_total = Counter(
    "ingest_transactions_total",
    "Total number of transactions stored in the database",
)

ingest_errors_total = Counter(
    "ingest_errors_total",
    "Total number of ingestion errors",
    ["error_type"],
)

ingest_block_lag_seconds = Gauge(
    "ingest_block_lag_seconds",
    "Seconds behind the latest Ethereum block",
)

ingest_iteration_duration_seconds = Histogram(
    "ingest_iteration_duration_seconds",
    "Time spent processing one block",
    buckets=[1, 2, 5, 10, 15, 20, 30, 60],
)


# ==============================================================
# RISK SCORING METRICS
# ==============================================================

risk_scored_total = Counter(
    "risk_scored_total",
    "Total transactions scored for risk",
)

risk_flagged_total = Counter(
    "risk_flagged_total",
    "Total transactions flagged as risky (score >= 20)",
)


# ==============================================================
# GROQ / AI METRICS
# ==============================================================

groq_requests_total = Counter(
    "groq_requests_total",
    "Total requests to Groq API",
    ["status"],
)

groq_request_duration_seconds = Histogram(
    "groq_request_duration_seconds",
    "Groq API request latency in seconds",
    buckets=[0.5, 1, 2, 3, 5, 10, 20],
)


# ==============================================================
# HELPERS
# ==============================================================

@contextmanager
def timer(histogram: Histogram, **labels):
    """Context manager to time an operation and record it in a histogram."""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        if labels:
            histogram.labels(**labels).observe(duration)
        else:
            histogram.observe(duration)


# ==============================================================
# ASGI APP FOR /metrics ENDPOINT
# ==============================================================

# This is a ready-to-mount ASGI app that serves Prometheus metrics
metrics_app = make_asgi_app()
