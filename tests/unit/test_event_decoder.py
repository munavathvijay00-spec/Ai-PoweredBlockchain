"""Deterministic receipt decoding regression tests."""
from src.blockchain.event_decoder import (
    APPROVAL, SWAP_V2, TRANSFER, TRANSFER_SINGLE, decode_log, decode_receipt,
)

A = "0x" + "1" * 40
B = "0x" + "2" * 40
TOKEN = "0x" + "a" * 40


def topic(address):
    return "0x" + "0" * 24 + address[2:]


def word(number):
    return "0x" + format(number, "064x")


def log(signature, indexed, data="0x"):
    return {"address": TOKEN, "topics": [signature, *indexed], "data": data,
            "logIndex": 2, "transactionHash": "0x" + "f" * 64}


def test_erc20_transfer_keeps_full_raw_amount():
    amount = 10**30 + 123
    event = decode_log(log(TRANSFER, [topic(A), topic(B)], word(amount)))
    assert event["raw_amount"] == str(amount)
    assert event["standard"] == "ERC20-compatible"
    assert event["metadata_verified"] is False
    assert event["symbol"] is None


def test_erc721_transfer():
    event = decode_log(log(TRANSFER, [topic(A), topic(B), word(99)]))
    assert event["standard"] == "ERC721-compatible"
    assert event["token_id"] == "99"


def test_erc20_approval():
    event = decode_log(log(APPROVAL, [topic(A), topic(B)], word(123)))
    assert event["event"] == "approval"
    assert event["spender"] == B


def test_v2_swap_not_mislabeled_verified():
    payload = "0x" + "".join(format(x, "064x") for x in [100, 0, 0, 75])
    event = decode_log(log(SWAP_V2, [topic(A), topic(B)], payload))
    assert event["amount0_in"] == "100"
    assert event["amount1_out"] == "75"
    assert event["protocol_verified"] is False


def test_malformed_log_is_counted_not_fabricated():
    receipt = {"transactionHash": "0x123", "status": 1,
               "logs": [log(TRANSFER, [topic(A), topic(B)], "0x12"),
                        log(TRANSFER, [topic(A), topic(B)], word(7))]}
    result = decode_receipt(receipt)
    assert result["invalid_logs"] == 1
    assert result["decoded_count"] == 1


def test_bounded_decoding_reports_truncation():
    receipt = {"status": 1, "logs": [log(TRANSFER, [topic(A), topic(B)], word(1))] * 3}
    result = decode_receipt(receipt, max_logs=2)
    assert result["truncated"] is True
    assert result["decoded_count"] == 2


def test_unknown_signature_is_not_assumed_token():
    assert decode_log(log("0x" + "0" * 64, [topic(A)])) is None


def test_erc1155_single():
    data = "0x" + format(44, "064x") + format(200, "064x")
    event = decode_log(log(TRANSFER_SINGLE, [topic(A), topic(A), topic(B)], data))
    assert event["standard"] == "ERC1155-compatible"
    assert event["token_id"] == "44"
    assert event["raw_amount"] == "200"
