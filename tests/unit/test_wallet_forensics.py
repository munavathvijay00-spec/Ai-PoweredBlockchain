from datetime import datetime, timedelta, timezone

from src.forensics.wallet_analysis import analyze_wallet, canonical_asset_key


ROOT = "0x" + "1" * 40
A = "0x" + "2" * 40
B = "0x" + "3" * 40
C = "0x" + "4" * 40
D = "0x" + "5" * 40


def row(i, source, target, minutes, asset="ETH", category="external", contract=None):
    return {
        "evidence_key": f"e{i}",
        "tx_hash": "0x" + f"{i:064x}",
        "category": category,
        "from_address": source,
        "to_address": target,
        "asset": asset,
        "value_text": "1",
        "token_id": None,
        "contract_address": contract,
        "block_number": 100 + i,
        "block_timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        "evidence_url": f"https://etherscan.io/tx/{i}",
    }


def test_canonical_asset_uses_contract_not_symbol():
    contract = "0x" + "a" * 40
    key = canonical_asset_key({"category": "erc20", "contract_address": contract, "asset": "USDC"})
    assert key == f"eip155:1/erc20:{contract}"


def test_detects_fan_out_and_reconvergence():
    rows = [
        row(1, ROOT, A, 0),
        row(2, ROOT, B, 1),
        row(3, ROOT, C, 2),
        row(4, A, D, 5),
        row(5, B, D, 6),
    ]
    result = analyze_wallet(ROOT, rows)
    codes = {item["code"] for item in result["findings"]}
    assert "fan_out" in codes
    assert "branch_reconvergence" in codes


def test_detects_rapid_forwarding_same_asset_only():
    rows = [row(1, A, ROOT, 0), row(2, ROOT, B, 10)]
    result = analyze_wallet(ROOT, rows, rapid_minutes=30)
    assert "rapid_forwarding" in {item["code"] for item in result["findings"]}


def test_does_not_mix_assets_for_forwarding():
    usdc = "0x" + "a" * 40
    rows = [
        row(1, A, ROOT, 0, asset="USDC", category="erc20", contract=usdc),
        row(2, ROOT, B, 10, asset="ETH", category="external"),
    ]
    result = analyze_wallet(ROOT, rows, rapid_minutes=30)
    assert "rapid_forwarding" not in {item["code"] for item in result["findings"]}
