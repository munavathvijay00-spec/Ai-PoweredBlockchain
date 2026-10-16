from pydantic import BaseModel

import src.api.browse_routes as browse


class DummyTransaction(BaseModel):
    hash: str
    relationship_context: dict


def test_cluster_metadata_is_added_after_model_serialization(monkeypatch):
    def fake_format(row, matches):
        return DummyTransaction(hash=row["hash"], relationship_context=row["relationship_context"])

    monkeypatch.setattr(browse, "_format_tx", fake_format)
    row = {
        "hash": "0xabc",
        "from_address": "0x1",
        "to_address": "0x2",
        "cluster_count": 3,
        "cluster_hashes": ["0xabc", "0xdef", "0x123"],
        "cluster_blocks": 2,
        "oldest_timestamp": None,
        "newest_timestamp": None,
    }
    result = browse._decorate_row(row, {}, True)
    assert isinstance(result, dict)
    assert result["hash"] == "0xabc"
    assert result["cluster"]["count"] == 3
    assert result["cluster"]["hashes"] == ["0xabc", "0xdef", "0x123"]
    assert result["relationship_context"]["same_pair_count"] == 3
