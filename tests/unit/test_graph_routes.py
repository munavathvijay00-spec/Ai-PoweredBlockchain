"""Graph tests use synthetic records; these are not mainnet validation."""

from src.api.graph_routes import _edge, _motifs


def test_edge_preserves_evidence_and_exact_wei():
    root = "0x" + "a" * 40
    other = "0x" + "b" * 40
    tx = "0x" + "c" * 64
    row = {
        "hash": tx,
        "block_number": 21000000,
        "value_wei": "999999999999999999999999999",
        "from_address": root,
        "to_address": other,
        "risk_score": 0,
    }
    edge = _edge(row, hop=1)
    assert edge["value_wei"] == row["value_wei"]
    assert edge["evidence_url"].endswith(tx)
    assert edge["source"] == root
    assert edge["target"] == other
    assert edge["relationship"] == "observed_native_transaction"
    assert edge["hop"] == 1


def test_empty_graph_motifs_do_not_invent_activity():
    motifs = _motifs([])
    assert motifs["fan_out"] == []
    assert motifs["fan_in"] == []
    assert motifs["reciprocal_pairs"] == []
