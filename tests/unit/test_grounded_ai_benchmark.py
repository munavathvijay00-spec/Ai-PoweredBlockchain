from scripts.evaluate_grounded_ai import evaluate_cases


BASELINE = (
    "Evidence-based transaction review: transaction 0xabc123 scored 35/100. "
    "Recorded evidence: [E1] repeated transfers in one observed block. "
    "These indicators warrant review but do not independently prove wrongdoing."
)


def case(case_id, candidate, expected_grounded):
    return {
        "case_id": case_id,
        "baseline": BASELINE,
        "candidate": candidate,
        "expected_grounded": expected_grounded,
    }


def test_grounded_ai_benchmark_separates_accepts_and_rejects():
    result = evaluate_cases([
        case(
            "faithful",
            "Transaction 0xabc123 scored 35/100 with repeated transfers observed in one block [E1]. These are review indicators, not proof of wrongdoing.",
            True,
        ),
        case(
            "invented-number",
            "Transaction 0xabc123 scored 35/100 after 99 repeated transfers [E1]. These are review indicators.",
            False,
        ),
        case(
            "invented-mixer",
            "Transaction 0xabc123 scored 35/100 and appears linked to a mixer [E1].",
            False,
        ),
        case(
            "missing-ref",
            "Transaction 0xabc123 scored 35/100 with repeated transfers observed in one block. These are review indicators, not proof of wrongdoing.",
            False,
        ),
    ])

    assert result["cases"] == 4
    assert result["confusion_matrix"] == {"tp": 1, "fp": 0, "tn": 3, "fn": 0}
    assert result["grounded_acceptance_precision"] == 1.0
    assert result["grounded_acceptance_recall"] == 1.0
    assert result["unsupported_claim_rejection_rate"] == 1.0
    assert result["false_accept_rate"] == 0.0
    assert result["false_reject_rate"] == 0.0
    assert result["reason_counts"]["invented_numeric_claim"] == 1
    assert result["reason_counts"]["missing_required_evidence_reference"] == 1


def test_duplicate_case_id_rejected():
    rows = [
        case("same", "Transaction 0xabc123 scored 35/100 [E1]. These are review indicators, not proof of wrongdoing.", True),
        case("same", "Transaction 0xabc123 scored 35/100 [E1]. These are review indicators, not proof of wrongdoing.", True),
    ]
    try:
        evaluate_cases(rows)
    except ValueError as error:
        assert "duplicate case_id" in str(error)
    else:
        raise AssertionError("duplicate case_id should be rejected")


def test_expected_grounded_must_be_independent_boolean_label():
    try:
        evaluate_cases([{
            "case_id": "bad-label",
            "baseline": BASELINE,
            "candidate": "Some candidate",
            "expected_grounded": "yes",
        }])
    except ValueError as error:
        assert "expected_grounded must be boolean" in str(error)
    else:
        raise AssertionError("non-boolean benchmark label should be rejected")
