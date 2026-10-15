"""Execute a configured flagship investigation using existing production code paths.

The case identifier is resolved from the packaged registry so the runtime and exported
provenance remain aligned.
"""
from __future__ import annotations

import json
from loguru import logger

from src.api.deep_history_routes import deep_sync_wallet_history
from src.api.flagship_routes import _find_case, flagship_package
from src.database.repositories import AddressRepository, TransactionRepository
from src.forensics.run_store import save_run


async def execute_case(db, case_id: str) -> dict:
    case = _find_case(case_id)
    address = str(case.get("address") or "").lower()
    if not address:
        raise ValueError("Flagship case is missing an address")

    repo = TransactionRepository(db, AddressRepository(db))
    sync = await deep_sync_wallet_history(
        address=address,
        max_batches=6,
        pages_per_batch=5,
        per_direction=50,
        include_internal=True,
        include_nfts=True,
        repo=repo,
    )
    logger.info(
        "Flagship sync case={} batches={} fetched={} inserted={} cached={} complete={}",
        case_id,
        sync.get("batches_run"),
        sync.get("provider_records_fetched"),
        sync.get("new_records_cached"),
        sync.get("records_cached"),
        sync.get("selected_category_history_complete"),
    )

    package = await flagship_package(
        case_id=case_id,
        include_ai=True,
        limit=5000,
        rapid_minutes=30,
        repo=repo,
    )
    summary = await save_run(db, case_id, package)
    summary.update({"case_id": case_id, "address": address})
    logger.info("Flagship investigation summary {}", json.dumps(summary, sort_keys=True, default=str))
    return summary
