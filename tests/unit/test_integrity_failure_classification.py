"""Chain integrity failures must stop the ingestion loop."""
import pytest
from src.ingest.loop import is_chain_integrity_failure


@pytest.mark.parametrize("message", [
    "REORG_DETECTED: checkpoint differs",
    "TRANSACTION_PROVENANCE_CONFLICT: 0x123 differs from stored transfer",
    "CHECKPOINT_CONFLICT: checkpoint did not advance",
])
def test_integrity_conflict_is_fatal(message):
    assert is_chain_integrity_failure(RuntimeError(message))


@pytest.mark.parametrize("message", [
    "temporary RPC timeout",
    "database connection refused",
    "normalization failed",
])
def test_transient_errors_are_not_classified_as_integrity_conflicts(message):
    assert not is_chain_integrity_failure(RuntimeError(message))
