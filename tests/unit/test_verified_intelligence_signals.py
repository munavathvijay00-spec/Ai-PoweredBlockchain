from src.risk.intelligence_signals import apply_verified_intelligence


def tx(sender=None, recipient=None):
    return {
        "from_address": sender or "0x" + "a" * 40,
        "to_address": recipient or "0x" + "b" * 40,
    }


def test_no_verified_match_preserves_score_and_factors():
    result = apply_verified_intelligence(
        {"score": 20, "factors": [{"factor": "notable_transaction"}]},
        tx(),
        {},
    )
    assert result["score"] == 20
    assert result["factors"] == [{"factor": "notable_transaction"}]


def test_exact_sender_match_is_source_attributed_and_critical_review():
    sender = "0x" + "a" * 40
    result = apply_verified_intelligence(
        {"score": 10, "factors": []},
        tx(sender=sender),
        {
            sender: {
                "source": "OFAC_SDN_ETH",
                "entity_id": "12345",
                "entity_name": "Example Listed Entity",
                "checked_at": "2026-10-14T00:00:00Z",
            }
        },
    )
    assert result["score"] == 100
    factor = result["factors"][0]
    assert factor["factor"] == "verified_sanctions_match"
    assert factor["source"] == "OFAC_SDN_ETH"
    assert factor["entity_id"] == "12345"
    assert factor["matched_address"] == sender
    assert factor["matched_role"] == "sender"
    assert "not proof of ownership or wrongdoing" in factor["reason"]


def test_exact_recipient_match_preserves_existing_evidence():
    recipient = "0x" + "b" * 40
    prior = {"factor": "large_transaction", "points": 30}
    result = apply_verified_intelligence(
        {"score": 30, "factors": [prior]},
        tx(recipient=recipient),
        {
            recipient: {
                "source": "OFAC_SDN_ETH",
                "entity_id": "67890",
                "entity_name": "Another Entity",
            }
        },
    )
    assert result["score"] == 100
    assert result["factors"][0] == prior
    assert result["factors"][1]["matched_role"] == "recipient"
