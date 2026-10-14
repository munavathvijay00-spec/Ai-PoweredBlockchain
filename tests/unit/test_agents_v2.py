import pytest

from src.agents.investigation_analyst import _validate
from src.agents.orchestrator import Orchestrator
from src.agents.pattern_agent import PatternAgent
from src.agents.tx_agent import TransactionAgent


class FakePatternTools:
    async def analyze_address_patterns(self, address):
        return {
            "address": address.lower(),
            "sample_size": 24,
            "outgoing_count": 15,
            "incoming_count": 9,
            "fan_out": 12,
            "fan_in": 7,
            "max_transactions_in_10m": 11,
            "reciprocal_counterparties": ["0x" + "2" * 40],
            "repeated_amounts": [{"value_wei": "1000", "count": 4}],
            "signals": [
                {"type": "bursty_activity", "severity": "review", "observed": 11, "window_minutes": 10},
                {"type": "fan_out", "severity": "review", "unique_outgoing_counterparties": 12},
            ],
            "coverage_note": "bounded retained data",
        }


class FakeTxTools:
    async def get_transaction_context(self, tx_hash):
        return {
            "transaction": {
                "hash": tx_hash,
                "from_address": "0x" + "1" * 40,
                "to_address": "0x" + "2" * 40,
                "value": 2 * 10**18,
                "block_number": 123,
                "risk_score": 55,
                "risk_factors": [{"reason": "Large retained transfer", "points": 20}],
            },
            "entity_matches": {},
            "nearby_activity": [{"hash": "0x" + "3" * 64}],
        }


def test_orchestrator_does_not_extract_address_from_tx_hash():
    tx_hash = "0x" + "a" * 64
    entities = Orchestrator()._extract_entities(f"explain {tx_hash}")
    assert entities == {"tx_hash": tx_hash}


def test_orchestrator_wallet_routes_account_and_pattern():
    address = "0x" + "b" * 40
    agents = Orchestrator()._select_agents(f"investigate wallet {address} behavior", {"address": address})
    assert agents == ["account", "pattern"]


def test_evidence_ledger_namespaces_specialist_evidence():
    ledger = Orchestrator._evidence_ledger([
        {"agent": "account_agent", "evidence": [{"id": "W1", "claim": "Balance is 1 ETH", "source": "rpc"}]},
        {"agent": "pattern_agent", "evidence": [{"id": "P1", "claim": "Observed 10 transfers", "source": "db"}]},
    ])
    assert [x["id"] for x in ledger] == ["account_agent:W1", "pattern_agent:P1"]


@pytest.mark.asyncio
async def test_pattern_agent_returns_explainable_motifs(monkeypatch):
    monkeypatch.setattr("src.agents.pattern_agent.get_tools", lambda: FakePatternTools())
    address = "0x" + "c" * 40
    result = await PatternAgent().handle("analyze behavior", {"address": address})
    assert result["status"] == "ok"
    assert {e["type"] for e in result["evidence"]} == {"bursty_activity", "fan_out"}
    assert "not establish illicit intent" in result["answer"]


@pytest.mark.asyncio
async def test_transaction_agent_uses_detector_and_nearby_evidence(monkeypatch):
    monkeypatch.setattr("src.agents.tx_agent.get_tools", lambda: FakeTxTools())
    tx_hash = "0x" + "d" * 64
    result = await TransactionAgent().handle("explain", {"tx_hash": tx_hash})
    assert result["status"] == "ok"
    assert result["data"]["risk_score"] == 55
    assert result["data"]["nearby_activity"]
    assert any(e["type"] == "detector_evidence" for e in result["evidence"])


def test_grounded_analyst_rejects_fake_evidence_reference():
    ledger = [{"id": "account_agent:W1", "claim": "Current balance is 1 ETH."}]
    payload = {
        "summary": "Wallet context",
        "claims": [{"text": "Balance is 1 ETH.", "evidence_ids": ["fake:E9"]}],
        "uncertainty": "This is bounded coverage and not proof of wrongdoing.",
    }
    result = _validate(payload, ledger)
    assert result["grounded"] is False
    assert any("invalid_evidence_reference" in reason for reason in result["reasons"])


def test_grounded_analyst_rejects_invented_numbers_and_sensitive_claims():
    ledger = [{"id": "tx_agent:T1", "claim": "Transaction moved 2 ETH in block 123."}]
    payload = {
        "summary": "Transaction context",
        "claims": [{"text": "The hacker moved 20 ETH in block 123.", "evidence_ids": ["tx_agent:T1"]}],
        "uncertainty": "Indicators are bounded and not proof of wrongdoing.",
    }
    result = _validate(payload, ledger)
    assert result["grounded"] is False
    assert "claim_0_unsupported_sensitive_term" in result["reasons"]
    assert "claim_0_invented_number" in result["reasons"]


def test_grounded_analyst_accepts_supported_claim():
    ledger = [{"id": "tx_agent:T1", "claim": "Transaction moved 2 ETH in block 123."}]
    payload = {
        "summary": "Observed transfer facts",
        "claims": [{"text": "Transaction moved 2 ETH in block 123.", "evidence_ids": ["tx_agent:T1"]}],
        "uncertainty": "Coverage is bounded; this is not proof of wrongdoing.",
    }
    assert _validate(payload, ledger)["grounded"] is True
