"""Evidence-first transaction risk scoring.

Scores are triage signals, not probabilities of fraud. Every behavioral factor
records the observation that caused it so explanations can cite evidence.
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone


class RiskScorer:
    def __init__(
        self,
        large_tx_threshold_eth: float = 10.0,
        bursty_window_minutes: int = 60,
        bursty_threshold: int = 10,
        new_wallet_days: int = 30,
    ):
        self.large_tx_threshold_wei = int(large_tx_threshold_eth * 10**18)
        self.bursty_window = timedelta(minutes=bursty_window_minutes)
        self.bursty_threshold = bursty_threshold
        self.new_wallet_days = new_wallet_days

    async def score_transaction(
        self,
        tx: Dict,
        address_history: List[Dict],
        is_blacklisted: bool = False,
        address_age_days: Optional[int] = None,
    ) -> Dict:
        score = 0
        factors = []

        if is_blacklisted:
            factors.append({
                "factor": "blacklisted_address",
                "points": 100,
                "reason": "Interacts with a manually verified blocked address",
                "source": "manual_blacklist",
            })
            return {"score": 100, "factors": factors}

        value_wei = int(tx.get("value", 0) or 0)
        value_eth = value_wei / 10**18
        if value_eth >= 1000:
            score += 40
            factors.append({
                "factor": "whale_transaction", "points": 40,
                "reason": f"{value_eth:,.4f} ETH transfer — whale amount tier",
                "observed_value_wei": str(value_wei),
            })
        elif value_eth >= 100:
            score += 30
            factors.append({
                "factor": "large_transaction", "points": 30,
                "reason": f"{value_eth:,.4f} ETH transfer — large amount tier",
                "observed_value_wei": str(value_wei),
            })
        elif value_eth >= 10:
            score += 20
            factors.append({
                "factor": "notable_transaction", "points": 20,
                "reason": f"{value_eth:,.4f} ETH transfer — notable amount tier",
                "observed_value_wei": str(value_wei),
            })
        elif value_eth >= 1:
            score += 10
            factors.append({
                "factor": "medium_transaction", "points": 10,
                "reason": f"{value_eth:,.4f} ETH transfer",
                "observed_value_wei": str(value_wei),
            })

        recent = self._recent(address_history)
        if self._detect_bursty(recent):
            score += 25
            factors.append({
                "factor": "bursty_activity",
                "points": 25,
                "reason": f"{len(recent)} observed transfers in the recent {int(self.bursty_window.total_seconds() // 60)} minute retained window",
                "observed_transfer_count": len(recent),
                "window_minutes": int(self.bursty_window.total_seconds() // 60),
            })

        ping_pong = self._ping_pong_evidence(recent)
        if ping_pong:
            score += 20
            factors.append({
                "factor": "ping_pong_pattern",
                "points": 20,
                "reason": "Bidirectional repeated transfers with the same counterparty in recent retained evidence",
                **ping_pong,
            })

        concentration = self._counterparty_concentration(recent)
        if concentration:
            score += 10
            factors.append({
                "factor": "repeated_counterparty",
                "points": 10,
                "reason": "Repeated recent interaction with one counterparty",
                **concentration,
            })

        if address_age_days is not None and address_age_days < self.new_wallet_days:
            score += 15
            factors.append({
                "factor": "new_wallet",
                "points": 15,
                "reason": f"Recipient wallet first observed {address_age_days} days ago",
                "observed_age_days": address_age_days,
            })

        outgoing_history = [
            h for h in address_history
            if h.get("direction") in (None, "outgoing")
        ]
        if outgoing_history:
            values = [int(h.get("value", 0) or 0) for h in outgoing_history]
            avg_value = sum(values) / len(values)
            if avg_value > 0 and value_wei > avg_value * 5:
                multiple = value_wei / avg_value
                score += 10
                factors.append({
                    "factor": "unusual_value",
                    "points": 10,
                    "reason": f"Transfer value is {multiple:.2f}x the sender's recent retained outgoing average",
                    "observed_multiple": round(multiple, 2),
                    "comparison_count": len(values),
                })

        # A zero-value native transaction is common for contract calls and
        # ERC-20 interactions. Record the context without automatically raising
        # review priority; no malicious behavior follows from zero ETH alone.
        if value_wei == 0:
            factors.append({
                "factor": "zero_value",
                "points": 0,
                "reason": "Zero native ETH; contract interaction is possible, token movement requires event evidence",
            })

        return {"score": min(score, 100), "factors": factors}

    def _recent(self, history: List[Dict]) -> List[Dict]:
        if not history:
            return []
        now = datetime.now(timezone.utc)
        window_start = now - self.bursty_window
        recent = []
        for item in history:
            timestamp = item.get("timestamp")
            if timestamp is None:
                # Preserve compatibility with older in-memory callers while not
                # treating missing timestamps as fresh production evidence.
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp >= window_start:
                recent.append(item)
        return recent

    def _detect_bursty(self, history: List[Dict]) -> bool:
        if not history:
            return False
        # Older unit/in-memory callers may pass already-windowed naive timestamps.
        if any(item.get("timestamp") is None for item in history):
            return len(history) > self.bursty_threshold
        recent = self._recent(history)
        return len(recent) > self.bursty_threshold

    def _ping_pong_evidence(self, history: List[Dict]):
        directional = [h for h in history if h.get("direction") and h.get("counterparty")]
        if not directional:
            return None
        by_counterparty = defaultdict(list)
        for item in directional:
            by_counterparty[str(item["counterparty"]).lower()].append(item)
        for counterparty, items in by_counterparty.items():
            incoming = sum(1 for item in items if item.get("direction") == "incoming")
            outgoing = sum(1 for item in items if item.get("direction") == "outgoing")
            ordered = sorted(items, key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))
            changes = sum(
                1 for previous, current in zip(ordered, ordered[1:])
                if previous.get("direction") != current.get("direction")
            )
            if incoming >= 2 and outgoing >= 2 and changes >= 3:
                return {
                    "counterparty": counterparty,
                    "incoming_count": incoming,
                    "outgoing_count": outgoing,
                    "direction_changes": changes,
                    "observed_transfer_count": len(items),
                }
        return None

    def _detect_ping_pong(self, history: List[Dict]) -> bool:
        evidence = self._ping_pong_evidence(history)
        if evidence:
            return True
        # Legacy compatibility for callers that provide only destination lists.
        if len(history) < 6 or any(h.get("direction") for h in history):
            return False
        addresses = [h.get("to_address", "") for h in history[:6]]
        return len(set(addresses)) <= 2

    def _counterparty_concentration(self, history: List[Dict]):
        counterparties = [str(h.get("counterparty")).lower() for h in history if h.get("counterparty")]
        if not counterparties:
            return None
        counterparty, count = Counter(counterparties).most_common(1)[0]
        if count >= 6:
            return {
                "counterparty": counterparty,
                "observed_transfer_count": count,
                "sample_size": len(counterparties),
            }
        return None


_scorer: Optional[RiskScorer] = None


def get_scorer() -> RiskScorer:
    global _scorer
    if _scorer is None:
        from src.utils.config import get_settings
        settings = get_settings()
        _scorer = RiskScorer(
            large_tx_threshold_eth=settings.large_transaction_threshold_eth,
            bursty_window_minutes=settings.bursty_activity_window_minutes,
            bursty_threshold=settings.bursty_activity_threshold,
            new_wallet_days=settings.new_wallet_days,
        )
    return _scorer
