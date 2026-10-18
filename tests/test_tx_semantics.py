from src.risk.tx_semantics import selector_candidate, summarize_transfer_semantics

def test_selector_only_is_not_verified_swap():
    finding = selector_candidate("0x38ed1739" + "0" * 64)
    assert finding["evidence_level"] == "method_selector_only"
    assert "swap" in finding["semantic"]

def test_token_multi_asset_cooccurrence_not_claimed_as_swap():
    h = "0x" + "1" * 64
    token = [
        {"tx_hash":h,"contract_address":"0x"+"a"*40,"asset":"AAA"},
        {"tx_hash":h,"contract_address":"0x"+"b"*40,"asset":"BBB"},
    ]
    result = summarize_transfer_semantics([], token)
    assert result[0]["classification"] == "multi_asset_transfer_evidence"
    assert result[0]["swap_confirmed"] is False
    assert result[0]["bridge_confirmed"] is False

def test_no_token_flow_means_no_candidate():
    assert summarize_transfer_semantics([{"tx_hash":"0x"+"1"*64}], []) == []
