"""Non-destructive ingestion and database health warnings."""
from loguru import logger
from src.metrics import ingest_head_block, ingest_checkpoint_block, ingest_block_lag_blocks, ingest_block_lag_seconds


def assess_ingestion_health(latest: int, checkpoint: int, *, warn_lag: int = 12) -> dict:
    """Return measurable chain lag without advancing or changing the cursor."""
    if warn_lag < 1:
        raise ValueError("warn_lag must be positive")
    lag = max(0, latest - checkpoint)
    return {
        "latest_block": latest,
        "checkpoint": checkpoint,
        "lag_blocks": lag,
        "warning": lag >= warn_lag,
        "chain_behind_checkpoint": latest < checkpoint,
    }


def assess_storage_health(logical_bytes: int, *, budget_mb: int = 500,
                          warn_percent: int = 70, critical_percent: int = 85) -> dict:
    """Estimate logical DB pressure; this is NOT physical Railway volume usage."""
    if budget_mb <= 0 or not (0 < warn_percent < critical_percent <= 100):
        raise ValueError("invalid storage warning thresholds")
    percent = logical_bytes * 100 / (budget_mb * 1048576)
    level = "critical" if percent >= critical_percent else "warning" if percent >= warn_percent else "ok"
    return {
        "logical_mb": round(logical_bytes / 1048576, 2),
        "budget_mb": budget_mb,
        "percent": round(percent, 1),
        "level": level,
    }


def log_ingestion_health(latest: int, checkpoint: int) -> dict:
    health = assess_ingestion_health(latest, checkpoint)
    ingest_head_block.set(latest)
    ingest_checkpoint_block.set(checkpoint)
    ingest_block_lag_blocks.set(health["lag_blocks"])
    # Ethereum targets roughly 12 second slots. This is an operational lag estimate,
    # not a claim about exact wall-clock age of every block.
    ingest_block_lag_seconds.set(health["lag_blocks"] * 12)
    if health["chain_behind_checkpoint"]:
        logger.warning("Ingestion health: chain head {} below checkpoint {}", latest, checkpoint)
    elif health["warning"]:
        logger.warning(
            "Ingestion lag warning: {} blocks behind head (checkpoint={} latest={})",
            health["lag_blocks"], checkpoint, latest,
        )
    else:
        logger.info(
            "Ingestion health: {} blocks behind head (checkpoint={} latest={})",
            health["lag_blocks"], checkpoint, latest,
        )
    return health
