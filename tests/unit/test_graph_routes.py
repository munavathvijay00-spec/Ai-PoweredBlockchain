"""Graph tests use synthetic records; these are not mainnet validation."""
from src.api.graph_routes import build_observed_graph


def test_observed_graph_preserves_evidence_and_exact_wei():
    root = "0x" + "a" * 40
    other = "0x" + "b" * 40
    tx = "0x" + "c" * 64
    rows = [{
        "hash": tx, "block_number": 21000000,
        "value_wei": "999999999999999999999999999",
        "from_address": root, "to_address": other,
    }]
    graph = build_observed_graph(root, rows, True)
    assert len(graph["nodes"]) == 2
    assert graph["edges"][0]["value_wei"] == rows[0]["value_wei"]
    assert graph["edges"][0]["evidence_url"].endswith(tx)
    assert graph["truncated"] is True
    assert graph["historical_completeness"] is False
    assert graph["depth"] == 1


def test_empty_graph_does_not_imply_inactive_wallet():
    root = "0x" + "a" * 40
    graph = build_observed_graph(root, [], False)
    assert graph["nodes"] == [{"id": root, "type": "address"}]
    assert graph["edges"] == []
    assert graph["historical_completeness"] is False
