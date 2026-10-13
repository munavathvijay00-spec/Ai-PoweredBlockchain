from src.agents.explainer import evidence_explanation, explanation_is_grounded


def test_evidence_explanation_uses_recorded_score_reason_and_reference():
    tx = {"risk_score": 35}
    factors = [{"factor": "same_block_fan_out", "points": 15, "reason": "High-volume transfers to many recipients within one observed block"}]
    text = evidence_explanation(tx, factors)
    assert "35/100" in text
    assert "[E1]" in text
    assert "High-volume transfers to many recipients within one observed block" in text
    assert "do not independently prove wrongdoing" in text


def test_grounding_accepts_faithful_rewrite_with_evidence_reference():
    baseline = "Rule-based risk assessment: this transaction scored 35/100. Recorded evidence: [E1] High-volume transfers to many recipients within one observed block. These indicators warrant review but do not independently prove wrongdoing."
    candidate = "This transaction scored 35/100 because high-volume transfers to many recipients were observed within one block [E1]. These are review signals, not proof of wrongdoing."
    assert explanation_is_grounded(candidate, baseline)


def test_grounding_rejects_rewrite_without_required_evidence_reference():
    baseline = "Rule-based risk assessment: this transaction scored 35/100. Recorded evidence: [E1] High-volume transfers to many recipients within one observed block. These indicators warrant review but do not independently prove wrongdoing."
    candidate = "This transaction scored 35/100 because high-volume transfers to many recipients were observed within one block. These are review signals, not proof of wrongdoing."
    assert not explanation_is_grounded(candidate, baseline)


def test_grounding_rejects_invented_evidence_reference():
    baseline = "Rule-based risk assessment: this transaction scored 35/100. Recorded evidence: [E1] Repeated transfers in one observed block. These indicators warrant review but do not independently prove wrongdoing."
    candidate = "This transaction scored 35/100 because repeated transfers were observed [E9]. These are review signals, not proof of wrongdoing."
    assert not explanation_is_grounded(candidate, baseline)


def test_grounding_rejects_unsupported_sensitive_claim():
    baseline = "Rule-based risk assessment: this transaction scored 35/100. Recorded evidence: [E1] High-volume transfers to many recipients within one observed block. These indicators warrant review but do not independently prove wrongdoing."
    candidate = "This transaction scored 35/100 and appears connected to a mixer [E1]. These are review signals."
    assert not explanation_is_grounded(candidate, baseline)


def test_grounding_rejects_new_numeric_claim():
    baseline = "Rule-based risk assessment: this transaction scored 35/100. Recorded evidence: [E1] Repeated transfers to the same recipient in one observed block. These indicators warrant review but do not independently prove wrongdoing."
    candidate = "This transaction scored 35/100 after 42 repeated transfers to one recipient [E1]. These are review signals."
    assert not explanation_is_grounded(candidate, baseline)


def test_missing_factors_abstains_from_ai_conclusion():
    text = evidence_explanation({"risk_score": 20}, [])
    assert "does not include a specific supporting factor" in text
    assert "AI conclusion would not be reliable" in text
