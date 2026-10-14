"""Prometheus metrics for ChainScope.

Metrics are deliberately factual: they describe system behavior and measured
validation results, never inferred fraud probability.
"""
import time
from contextlib import contextmanager
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

# Ingestion / canonical-chain health
ingest_blocks_total = Counter("ingest_blocks_total", "Canonical blocks successfully ingested")
ingest_transactions_total = Counter("ingest_transactions_total", "Transactions stored by canonical ingestion")
ingest_errors_total = Counter("ingest_errors_total", "Ingestion errors", ["error_type"])
ingest_integrity_halts_total = Counter("ingest_integrity_halts_total", "Fail-closed canonical integrity halts", ["reason"])
ingest_block_lag_seconds = Gauge("ingest_block_lag_seconds", "Approximate seconds behind Ethereum head")
ingest_block_lag_blocks = Gauge("ingest_block_lag_blocks", "Blocks behind Ethereum head")
ingest_head_block = Gauge("ingest_head_block", "Latest Ethereum block observed by the worker")
ingest_checkpoint_block = Gauge("ingest_checkpoint_block", "Last durably checkpointed canonical block")
ingest_last_success_unixtime = Gauge("ingest_last_success_unixtime", "Unix timestamp of last successful block commit")
ingest_iteration_duration_seconds = Histogram(
    "ingest_iteration_duration_seconds", "Time spent processing one block",
    buckets=[0.5, 1, 2, 5, 10, 15, 20, 30, 60],
)

# RPC health
rpc_requests_total = Counter("rpc_requests_total", "Ethereum RPC requests", ["method", "status"])
rpc_request_duration_seconds = Histogram(
    "rpc_request_duration_seconds", "Ethereum RPC latency", ["method"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20],
)
rpc_connected = Gauge("rpc_connected", "1 when the latest RPC connection check succeeded")

# API / database health
api_requests_total = Counter("api_requests_total", "HTTP API requests", ["method", "route", "status"])
api_request_duration_seconds = Histogram(
    "api_request_duration_seconds", "HTTP API request latency", ["method", "route"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)
db_health_up = Gauge("db_health_up", "1 when the most recent DB health probe succeeded")
db_health_latency_seconds = Histogram(
    "db_health_latency_seconds", "Database health-probe latency",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2],
)

# Risk scoring / measurable evaluation
risk_scored_total = Counter("risk_scored_total", "Transactions scored for review risk")
risk_flagged_total = Counter("risk_flagged_total", "Transactions crossing the configured review threshold")
risk_benchmark_precision = Gauge("risk_benchmark_precision", "Measured precision on independently labelled reviewed cases")
risk_benchmark_recall = Gauge("risk_benchmark_recall", "Measured recall on independently labelled cases")
risk_benchmark_coverage = Gauge("risk_benchmark_coverage", "Fraction of labelled cases receiving a review prediction")
risk_benchmark_sample_size = Gauge("risk_benchmark_sample_size", "Independent labelled cases in latest benchmark")

# AI / explanation health
ai_explanations_total = Counter("ai_explanations_total", "Explanation outcomes", ["provider", "status"])
ai_grounding_rejections_total = Counter("ai_grounding_rejections_total", "LLM outputs rejected by grounding validation", ["provider"])
ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds", "LLM request latency", ["provider"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 60],
)
# Backward-compatible Groq metrics
groq_requests_total = Counter("groq_requests_total", "Groq API requests", ["status"])
groq_request_duration_seconds = Histogram(
    "groq_request_duration_seconds", "Groq API request latency",
    buckets=[0.5, 1, 2, 3, 5, 10, 20],
)

# Historical / entity enrichment
historical_provider_requests_total = Counter(
    "historical_provider_requests_total", "Historical wallet-provider requests", ["provider", "status"]
)
entity_lookup_total = Counter("entity_lookup_total", "Entity-attribution lookup outcomes", ["status"])


@contextmanager
def timer(histogram: Histogram, **labels):
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        target = histogram.labels(**labels) if labels else histogram
        target.observe(duration)


metrics_app = make_asgi_app()
