from src.risk.receipt_semantics import decode_receipt_evidence, ERC20_TRANSFER_TOPIC

H = "0x" + "a" * 64
def topic(address): return "0x" + "0" * 24 + address[2:]

def test_decodes_confirmed_receipt_transfer_candidate():
    sender, recipient = "0x"+"1"*40,"0x"+"2"*40
    receipt={"status":1,"blockNumber":123,"gasUsed":21000,"logs":[{
        "address":"0x"+"3"*40,"topics":[ERC20_TRANSFER_TOPIC,topic(sender),topic(recipient)],
        "data":"0x"+hex(100)[2:].zfill(64),"logIndex":0,
    }]}
    tx={"from":sender,"to":recipient,"input":"0xa9059cbb","value":0}
    result=decode_receipt_evidence(H,tx,receipt)
    assert result["receipt_status"]=="success"
    assert result["decoded_event_candidates"][0]["raw_uint256"]=="100"
    assert result["decoded_event_candidates"][0]["to_or_spender"]==recipient
    assert not result["swap_confirmed"]
    assert not result["internal_transfers_complete"]

def test_does_not_treat_erc721_transfer_as_erc20():
    receipt={"status":1,"logs":[{"address":"0x"+"3"*40,"topics":[ERC20_TRANSFER_TOPIC,topic("0x"+"1"*40),topic("0x"+"2"*40),"0x"+"0"*64],"data":"0x"}]}
    result=decode_receipt_evidence(H,{"input":"0x","value":0},receipt)
    assert result["decoded_event_candidates"]==[]
    assert result["skipped_ambiguous_events"]==1

def test_reverted_receipt_never_claims_swap():
    result=decode_receipt_evidence(H,{"input":"0x38ed1739","value":2},{"status":0,"logs":[]})
    assert result["receipt_status"]=="reverted"
    assert result["method_selector"]["evidence_level"]=="method_selector_only"
    assert result["swap_confirmed"] is False
