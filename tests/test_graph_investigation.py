from src.api.graph_routes import _directed_paths, _motifs


def edge(source, target, tx_hash, value_wei="1", risk_score=0, hop=1):
    return {
        "source": source,
        "target": target,
        "tx_hash": tx_hash,
        "block_number": 1,
        "value_wei": value_wei,
        "risk_score": risk_score,
        "hop": hop,
        "asset": "ETH",
        "chain_id": 1,
        "relationship": "observed_native_transaction",
    }


def test_directed_paths_are_bounded_and_preserve_transaction_evidence():
    root = "0x" + "1" * 40
    a = "0x" + "2" * 40
    b = "0x" + "3" * 40
    c = "0x" + "4" * 40
    edges = [
        edge(root, a, "0x" + "a" * 64, "10", 10, 1),
        edge(a, b, "0x" + "b" * 64, "20", 40, 2),
        edge(b, c, "0x" + "c" * 64, "30", 70, 3),
    ]

    paths = _directed_paths(root, edges, max_depth=2)
    assert paths
    assert max(item["hop_count"] for item in paths) == 2
    second_hop = next(item for item in paths if item["hop_count"] == 2)
    assert second_hop["tx_hashes"] == ["0x" + "a" * 64, "0x" + "b" * 64]
    assert second_hop["addresses"] == [root, a, b]
    assert second_hop["total_value_wei"] == "30"
    assert second_hop["max_risk_score"] == 40
    assert second_hop["relationship"] == "observed_directed_path"


def test_graph_motifs_report_observed_structure_without_verdicts():
    root = "0x" + "1" * 40
    a = "0x" + "2" * 40
    b = "0x" + "3" * 40
    c = "0x" + "4" * 40
    edges = [
        edge(root, a, "0x" + "a" * 64),
        edge(root, b, "0x" + "b" * 64),
        edge(root, c, "0x" + "c" * 64),
        edge(a, root, "0x" + "d" * 64),
    ]

    motifs = _motifs(edges)
    assert motifs["fan_out"][0] == {"address": root, "edge_count": 3}
    assert {motifs["reciprocal_pairs"][0]["a"], motifs["reciprocal_pairs"][0]["b"]} == {root, a}
    assert "not fraud verdicts" in motifs["note"]
