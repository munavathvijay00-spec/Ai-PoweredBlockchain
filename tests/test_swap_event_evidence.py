from src.risk.swap_event_evidence import V2_SWAP_TOPIC, V3_SWAP_TOPIC, decode_swap_event_candidate
from src.risk.receipt_semantics import decode_receipt_evidence

H = "0x" + "a" * 64
PAIR = "0x" + "b" * 40
SENDER = "0x" + "1" * 40
RECIPIENT = "0x" + "2" * 40

def word(value):
    return format(value % (2**256), "064x")

def addr_topic(address):
    return "0x" + "0" * 24 + address[2:]

def event(topic, amounts):
    return {
        "address": PAIR,
        "topics": [topic, addr_topic(SENDER), addr_topic(RECIPIENT)],
        "data": "0x" + "".join(word(number) for number in amounts),
        "logIndex": 7,
    }

def test_v2_swap_abi_data_and_direction():
    record = decode_swap_event_candidate(event(V2_SWAP_TOPIC, [10, 0, 0, 95]))
    assert record["abi_shape"] == "v2_abi"
    assert record["raw_amounts"]["amount0_in"] == "10"
    assert record["raw_amounts"]["amount1_out"] == "95"
    assert record["sender"] == SENDER and record["recipient"] == RECIPIENT
    assert record["pool_identity_verified"] is False
    assert record["swap_confirmed"] is False

def test_v3_signed_deltas_and_tick():
    record = decode_swap_event_candidate(event(V3_SWAP_TOPIC, [1000, -990, 2**96, 12345, -35]))
    assert record["abi_shape"] == "v3_abi"
    assert record["raw_amounts"]["amount0_delta_raw"] == "1000"
    assert record["raw_amounts"]["amount1_delta_raw"] == "-990"
    assert record["raw_amounts"]["tick"] == "-35"

def test_malformed_or_spoofed_shape_is_rejected():
    bad = event(V3_SWAP_TOPIC, [10, 20, 30])
    assert decode_swap_event_candidate(bad) is None
    bad = event(V2_SWAP_TOPIC, [10, 20, 30, 40])
    bad["topics"][1] = "0x" + "1" * 64
    assert decode_swap_event_candidate(bad) is None
    bad = event(V3_SWAP_TOPIC, [10, 20, 2**161, 100, 0])
    assert decode_swap_event_candidate(bad) is None

def test_reverted_receipt_cannot_prove_executed_swap():
    result = decode_receipt_evidence(H, {"input": "0x38ed1739", "value": 0}, {
        "status": 0,
        "logs": [event(V2_SWAP_TOPIC, [10, 0, 0, 9])],
    })
    assert result["receipt_status"] == "reverted"
    assert result["swap_confirmed"] is False
    assert result["swap_event_candidates"][0]["swap_confirmed"] is False

def test_successful_swap_shaped_log_is_evidence_not_attribution():
    result = decode_receipt_evidence(H, {"input": "0x", "value": 0}, {
        "status": 1, "logs": [event(V3_SWAP_TOPIC, [10, -9, 2**96, 100, 1])],
    })
    assert result["swap_event_candidates"][0]["pool_identity_verified"] is False
    assert result["bridge_confirmed"] is False
