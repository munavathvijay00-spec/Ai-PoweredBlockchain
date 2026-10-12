"""Hash serialization tests; full reorg integration requires an RPC fixture."""
from src.ingest.loop import _block_hash


def test_block_hash_bytes_and_strings():
    expected = "0x" + "ab" * 32
    assert _block_hash(bytes.fromhex("ab" * 32)) == expected
    assert _block_hash(expected) == expected
    assert _block_hash(expected[2:]) == expected
