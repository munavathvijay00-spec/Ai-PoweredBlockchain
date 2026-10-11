"""
Risk scoring engine.
Assigns each transaction a 0-100 risk score based on multiple heuristics.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class RiskScorer:
    """
    Calculates risk scores for blockchain transactions.
    """

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
        """Calculate risk score for a transaction."""
        score = 0
        factors = []

        if is_blacklisted:
            factors.append({
                "factor": "blacklisted_address",
                "points": 100,
                "reason": "Interacts with known bad actor"
            })
            return {"score": 100, "factors": factors}

                value_wei = tx.get('value', 0) or 0
        value_eth = value_wei / 10**18

        if value_eth >= 1000:
            score += 40
            factors.append({
                "factor": "whale_transaction",
                "points": 40,
                "reason": f"{value_eth:,.0f} ETH transfer — whale tier"
            })
        elif value_eth >= 100:
            score += 30
            factors.append({
                "factor": "large_transaction",
                "points": 30,
                "reason": f"{value_eth:,.1f} ETH transfer — large tier"
            })
        elif value_eth >= 10:
            score += 20
            factors.append({
                "factor": "notable_transaction",
                "points": 20,
                "reason": f"{value_eth:,.2f} ETH transfer — notable tier"
            })
        elif value_eth >= 1:
            score += 10
            factors.append({
                "factor": "medium_transaction",
                "points": 10,
                "reason": f"{value_eth:,.4f} ETH transfer"
            })

        if self._detect_bursty(address_history):
            score += 25
            factors.append({
                "factor": "bursty_activity",
                "points": 25,
                "reason": f">{self.bursty_threshold} txs in last hour"
            })

        if self._detect_ping_pong(address_history):
            score += 20
            factors.append({
                "factor": "ping_pong_pattern",
                "points": 20,
                "reason": "Rapid back-and-forth between same addresses"
            })

        if address_age_days is not None and address_age_days < self.new_wallet_days:
            score += 15
            factors.append({
                "factor": "new_wallet",
                "points": 15,
                "reason": f"Recipient wallet is {address_age_days} days old"
            })

        if address_history:
            avg_value = sum(h.get('value', 0) for h in address_history) / len(address_history)
            if avg_value > 0 and tx.get('value', 0) > avg_value * 5:
                score += 10
                factors.append({
                    "factor": "unusual_value",
                    "points": 10,
                    "reason": "Value 5x larger than sender's average"
                })

        if tx.get('value', 0) == 0:
            score += 5
            factors.append({
                "factor": "zero_value",
                "points": 5,
                "reason": "Zero-value transaction (contract call)"
            })

        final_score = min(score, 100)
        return {"score": final_score, "factors": factors}

    def _detect_bursty(self, history: List[Dict]) -> bool:
        """Detect many transactions in a short window."""
        if not history:
            return False
        now = datetime.now()
        window_start = now - self.bursty_window
        recent = [h for h in history if h.get('timestamp', now) >= window_start]
        return len(recent) > self.bursty_threshold

    def _detect_ping_pong(self, history: List[Dict]) -> bool:
        """Detect ping-pong pattern: back-and-forth between 2 addresses."""
        if len(history) < 6:
            return False
        recent = history[:6]
        addresses = [h.get('to_address', '') for h in recent]
        unique_addresses = set(addresses)
        return len(unique_addresses) <= 2


_scorer: Optional[RiskScorer] = None


def get_scorer() -> RiskScorer:
    """Get or create the global scorer instance."""
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