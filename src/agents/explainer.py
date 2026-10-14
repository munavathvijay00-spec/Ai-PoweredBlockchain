"""Grounded transaction explanations with optional LLM wording.

The model is never allowed to become a source of facts. Stored risk factors remain the
source of truth; any model-generated wording that introduces unsupported claims or
numbers is rejected and replaced by the deterministic evidence explanation.
"""
import asyncio
import re
import time
from typing import Dict, List, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import get_settings

_OVERCLAIM_PHRASES = (
    "definitely", "certainly", "confirmed fraud", "confirmed illicit",
    "is fraudulent", "is a scam", "criminal activity", "money laundering",
    "stolen funds", "malicious actor",
)

_SENSITIVE_CLAIM_TERMS = (
    "mixer", "tornado", "sanction", "ofac", "hack", "hacker", "scam", "phishing",
    "stolen", "launder", "criminal", "fraud", "malicious", "exchange", "bridge",
    "darknet", "ransomware",
)


def _normalized_numbers(text: str) -> set[str]:
    """Extract claimed numbers while ignoring hexadecimal hashes/addresses and evidence IDs."""
    without_hex = re.sub(r"0x[a-fA-F0-9]+", "", text or "")
    without_refs = re.sub(r"\[E\d+\]", "", without_hex)
    values = re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", without_refs)
    return {value.replace(",", "") for value in values}


def _evidence_refs(text: str) -> set[str]:
    return set(re.findall(r"\[E\d+\]", text or ""))


def _short_identifier(value: object, head: int = 10, tail: int = 8) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}…{text[-tail:]}"


def _eth_value_text(tx: Dict) -> Optional[str]:
    """Return a stable transaction-specific ETH amount without floating-point rounding drift."""
    raw = tx.get("value_wei", tx.get("value"))
    if raw is not None:
        try:
            wei = int(raw)
            whole = wei // 10**18
            fraction = str(wei % 10**18).rjust(18, "0").rstrip("0")
            return f"{whole:,}{'.' + fraction if fraction else ''} ETH"
        except (TypeError, ValueError, OverflowError):
            pass

    value_eth = tx.get("value_eth")
    try:
        if value_eth is not None:
            numeric = float(value_eth)
            return f"{numeric:,.8f}".rstrip("0").rstrip(".") + " ETH"
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _transaction_context(tx: Dict) -> str:
    """Build concise, factual context so explanations are specific to one transaction."""
    pieces: List[str] = []
    tx_hash = tx.get("hash")
    if tx_hash:
        pieces.append(f"transaction {_short_identifier(tx_hash, 12, 10)}")
    block_number = tx.get("block_number")
    if block_number is not None:
        try:
            pieces.append(f"block {int(block_number):,}")
        except (TypeError, ValueError, OverflowError):
            pass
    amount = _eth_value_text(tx)
    if amount:
        pieces.append(f"value {amount}")
    from_address = tx.get("from_address")
    to_address = tx.get("to_address")
    if from_address:
        pieces.append(f"from {_short_identifier(from_address)}")
    if to_address:
        pieces.append(f"to {_short_identifier(to_address)}")
    return ", ".join(pieces)


def _specificity_tokens(tx: Optional[Dict]) -> list[str]:
    """Return stable factual tokens a rewrite can preserve to prove it is transaction-specific."""
    if not tx:
        return []
    tokens: list[str] = []
    if tx.get("hash"):
        tokens.append(_short_identifier(tx["hash"], 12, 10))
    if tx.get("block_number") is not None:
        try:
            block = int(tx["block_number"])
            tokens.extend([str(block), f"{block:,}"])
        except (TypeError, ValueError, OverflowError):
            pass
    amount = _eth_value_text(tx)
    if amount:
        tokens.append(amount)
    if tx.get("from_address"):
        tokens.append(_short_identifier(tx["from_address"]))
    if tx.get("to_address"):
        tokens.append(_short_identifier(tx["to_address"]))
    return [token for token in tokens if token and token != "unknown"]


def grounding_report(candidate: str, baseline: str, tx: Optional[Dict] = None) -> Dict:
    """Return machine-readable grounding checks for one candidate rewrite."""
    reasons: list[str] = []
    checks = {
        "candidate_shape": False,
        "no_overclaim": False,
        "sensitive_claims_supported": False,
        "numbers_supported": False,
        "evidence_refs_supported": False,
        "evidence_ref_preserved": False,
        "transaction_specific": False if tx else True,
    }

    if not isinstance(candidate, str):
        reasons.append("candidate_not_text")
        return {"grounded": False, "checks": checks, "reasons": reasons}

    text = candidate.strip()
    if 20 <= len(text) <= 700:
        checks["candidate_shape"] = True
    else:
        reasons.append("candidate_length_out_of_bounds")

    lowered = text.lower()
    baseline_lower = (baseline or "").lower()
    if not any(phrase in lowered for phrase in _OVERCLAIM_PHRASES) and not (
        "proves" in lowered and "does not prove" not in lowered and "not proof" not in lowered
    ):
        checks["no_overclaim"] = True
    else:
        reasons.append("unsupported_overclaim")

    unsupported_sensitive = [
        term for term in _SENSITIVE_CLAIM_TERMS
        if term in lowered and term not in baseline_lower
    ]
    if not unsupported_sensitive:
        checks["sensitive_claims_supported"] = True
    else:
        reasons.append("unsupported_sensitive_claim:" + ",".join(sorted(unsupported_sensitive)))

    if _normalized_numbers(text).issubset(_normalized_numbers(baseline)):
        checks["numbers_supported"] = True
    else:
        reasons.append("invented_numeric_claim")

    baseline_refs = _evidence_refs(baseline)
    candidate_refs = _evidence_refs(text)
    if candidate_refs.issubset(baseline_refs):
        checks["evidence_refs_supported"] = True
    else:
        reasons.append("invented_evidence_reference")

    if not baseline_refs or candidate_refs:
        checks["evidence_ref_preserved"] = True
    else:
        reasons.append("missing_required_evidence_reference")

    if tx:
        tokens = _specificity_tokens(tx)
        if not tokens or any(token.lower() in lowered for token in tokens):
            checks["transaction_specific"] = True
        else:
            reasons.append("missing_transaction_specific_context")

    grounded = all(checks.values())
    return {
        "grounded": grounded,
        "checks": checks,
        "reasons": reasons,
        "baseline_evidence_refs": sorted(baseline_refs),
        "candidate_evidence_refs": sorted(candidate_refs),
    }


def explanation_is_grounded(candidate: str, baseline: str, tx: Optional[Dict] = None) -> bool:
    """Reject LLM wording that adds facts or loses required transaction-specific context."""
    return bool(grounding_report(candidate, baseline, tx).get("grounded"))


def evidence_explanation(tx: Dict, factors: List[Dict]) -> str:
    """Deterministic explanation assembled only from transaction facts and stored scoring evidence."""
    score = max(0, min(100, int(tx.get("risk_score") or 0)))
    context = _transaction_context(tx)
    reasons: List[str] = []
    for factor in factors or []:
        reason = str(factor.get("reason") or "").strip().rstrip(".")
        if reason:
            points = factor.get("points")
            if points is not None:
                try:
                    reason = f"{reason} (+{int(points)} points)"
                except (TypeError, ValueError, OverflowError):
                    pass
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) == 3:
            break

    subject = f"For {context}, " if context else "For this transaction, "
    if reasons:
        cited_reasons = "; ".join(
            f"[E{index}] {reason}" for index, reason in enumerate(reasons, start=1)
        )
        return (
            f"Evidence-based transaction review: {subject}the recorded risk score is {score}/100. "
            f"Recorded evidence: {cited_reasons}. "
            "These indicators warrant review but do not independently prove wrongdoing."
        )
    return (
        f"Evidence-based transaction review: {subject}the recorded risk score is {score}/100. "
        "The available scoring data does not include a specific supporting factor; "
        "an AI conclusion would not be reliable, so review the raw transaction evidence before drawing conclusions."
    )


class TransactionExplainer:
    """Optionally rewrites a deterministic evidence explanation without adding facts."""

    def __init__(self):
        self.settings = get_settings()
        self.provider = str(self.settings.llm_provider or "disabled").lower()
        self.model = (
            self.settings.groq_model if self.provider == "groq"
            else self.settings.llm_model
        )
        self.ollama_url = self.settings.ollama_url
        self._semaphore = asyncio.Semaphore(3)
        logger.info(f"🧠 Grounded explainer initialized (provider={self.provider}, model={self.model})")

    def _build_prompt(self, tx: Dict, factors: List[Dict]) -> str:
        baseline = evidence_explanation(tx, factors)
        return f"""You are editing an evidence-grounded Ethereum transaction explanation.

SOURCE OF TRUTH:
{baseline}

Rules:
- Rewrite the source into at most 2 short sentences for a non-technical user.
- Use ONLY facts already present in SOURCE OF TRUTH.
- Keep the exact risk score and any numeric evidence unchanged.
- Preserve at least one applicable [E#] evidence reference and never invent a new reference.
- Preserve at least one transaction-specific fact (transaction identifier, block, amount, sender, or recipient) so same-score transactions remain distinguishable.
- Do not infer identity, ownership, intent, fraud, sanctions, scams, hacks, theft, laundering, exchange usage, mixer usage, or historical behavior unless SOURCE OF TRUTH explicitly states it.
- Do not convert values to USD or add market prices.
- State that the signals are review indicators, not proof of wrongdoing.
- If a faithful rewrite is not possible, return exactly: UNSAFE_TO_REWRITE

Return only the explanation text."""

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def _call_ollama(self, prompt: str) -> str:
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 180, "top_p": 0.8},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json().get("response", "").strip()

    async def _call_groq(self, prompt: str) -> Optional[str]:
        from src.agents.providers.groq import get_groq_provider
        settings = getattr(self, "settings", None)
        api_key = getattr(settings, "groq_api_key", "not-set")
        model = getattr(self, "model", None) or getattr(settings, "groq_model", "openai/gpt-oss-20b")
        provider = get_groq_provider(api_key=api_key, model=model)
        return await provider.generate(prompt)

    def _provider_configured(self) -> bool:
        provider = str(getattr(self, "provider", "disabled") or "disabled").lower()
        if provider == "ollama":
            return True
        if provider == "groq":
            settings = getattr(self, "settings", None)
            api_key = str(getattr(settings, "groq_api_key", "not-set") or "").strip().lower()
            return api_key not in {"", "not-set", "none", "null", "placeholder", "changeme"}
        return False

    async def explain_with_audit(self, tx: Dict, factors: List[Dict]) -> Dict:
        """Return explanation plus proof of whether a real model produced accepted wording."""
        baseline = evidence_explanation(tx, factors)
        provider = str(getattr(self, "provider", "disabled") or "disabled").lower()
        model = getattr(self, "model", None)
        base_result = {
            "provider": provider,
            "model": model,
            "baseline": baseline,
            "explanation": baseline,
            "candidate": None,
            "ai_used": False,
            "grounded": True,
            "latency_ms": 0,
            "grounding_report": {
                "grounded": True,
                "checks": {},
                "reasons": ["deterministic_evidence_fallback"],
            },
        }

        if not factors:
            return {**base_result, "status": "abstained_no_evidence"}
        if not self._provider_configured():
            return {**base_result, "status": "provider_not_configured"}

        started = time.monotonic()
        candidate: Optional[str] = None
        try:
            prompt = self._build_prompt(tx, factors)
            async with self._semaphore:
                if provider == "ollama":
                    candidate = await self._call_ollama(prompt)
                elif provider == "groq":
                    candidate = await self._call_groq(prompt)
                else:
                    return {**base_result, "status": "provider_not_configured"}
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            logger.warning(f"AI explanation unavailable ({type(exc).__name__}); using deterministic evidence")
            return {
                **base_result,
                "status": "provider_no_output",
                "latency_ms": elapsed,
                "grounding_report": {
                    "grounded": False,
                    "checks": {},
                    "reasons": [f"provider_exception:{type(exc).__name__}"],
                },
            }

        elapsed = int((time.monotonic() - started) * 1000)
        if not isinstance(candidate, str) or not candidate.strip() or candidate.strip() == "UNSAFE_TO_REWRITE":
            return {
                **base_result,
                "status": "provider_no_output",
                "candidate": candidate.strip() if isinstance(candidate, str) else None,
                "latency_ms": elapsed,
                "grounding_report": {
                    "grounded": False,
                    "checks": {},
                    "reasons": ["provider_returned_no_usable_output"],
                },
            }

        candidate = candidate.strip()
        report = grounding_report(candidate, baseline, tx)
        if not report["grounded"]:
            logger.warning("Rejected ungrounded AI explanation; using deterministic evidence")
            return {
                **base_result,
                "status": "grounding_rejected",
                "candidate": candidate,
                "latency_ms": elapsed,
                "grounding_report": report,
            }

        return {
            **base_result,
            "status": "grounded_ai",
            "candidate": candidate,
            "explanation": f"Grounded AI explanation: {candidate}",
            "ai_used": True,
            "grounded": True,
            "latency_ms": elapsed,
            "grounding_report": report,
        }

    async def explain(self, tx: Dict, factors: List[Dict]) -> str:
        """Backward-compatible string result for ingestion and existing callers."""
        result = await self.explain_with_audit(tx, factors)
        return str(result["explanation"])


_explainer: Optional[TransactionExplainer] = None


def get_explainer() -> TransactionExplainer:
    global _explainer
    if _explainer is None:
        _explainer = TransactionExplainer()
    return _explainer
