from src.ingest.worker import build_ai_explanation_tasks


class ExplainerThatMustNotRun:
    def explain(self, tx, factors):
        raise AssertionError("external AI must not be invoked when disabled")


def test_disabled_external_ai_returns_no_tasks_and_never_calls_explainer():
    flagged = [{
        "hash": "0x" + "1" * 64,
        "score": 40,
        "factors": [],
    }]
    tx_by_hash = {
        flagged[0]["hash"]: {
            "hash": flagged[0]["hash"],
            "from_address": "0x" + "2" * 40,
            "to_address": "0x" + "3" * 40,
            "value_eth": 1.0,
            "block_number": 1,
        }
    }

    tasks, scores = build_ai_explanation_tasks(
        flagged,
        tx_by_hash,
        ExplainerThatMustNotRun(),
        allow_external_ai=False,
    )

    assert tasks == []
    assert scores == []
