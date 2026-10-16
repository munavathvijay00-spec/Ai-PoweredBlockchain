from src.api.graph_routes import _directed_paths


def test_directed_paths_preserve_evidence_and_conservative_value():
    root = "0x" + "1" * 40
    mid = "0x" + "2" * 40
    end = "0x" + "3" * 40
    edges = [
        {"source": root, "target": mid, "tx_hash": "0xaaa", "value_wei": "100", "risk_score": 20},
        {"source": mid, "target": end, "tx_hash": "0xbbb", "value_wei": "40", "risk_score": 70},
    ]
    paths = _directed_paths(root, edges, max_depth=2, max_paths=10)
    two_hop = next(item for item in paths if item["hop_count"] == 2)
    assert two_hop["addresses"] == [root, mid, end]
    assert two_hop["tx_hashes"] == ["0xaaa", "0xbbb"]
    assert two_hop["path_min_value_wei"] == "40"
    assert two_hop["path_sum_value_wei"] == "140"
    assert two_hop["max_risk_score"] == 70
