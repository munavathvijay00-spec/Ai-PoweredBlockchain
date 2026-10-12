"""Explainable, bounded same-block transaction behavior signals.

These signals use only transactions actually observed in the fetched block.
They do not imply criminality or claim full wallet history.
"""
from collections import Counter, defaultdict

MIN_BURST_TRANSFERS = 12
MIN_DISTINCT_RECIPIENTS = 8
MIN_REPEAT_TRANSFERS = 6


def analyze_block_behavior(transactions):
    """Return per-hash behavioral factors; O(n) time and bounded per-block memory."""
    by_sender = defaultdict(list)
    by_pair = defaultdict(list)
    for tx in transactions:
        sender = tx["from_address"].lower()
        recipient = tx["to_address"].lower()
        if sender == recipient:
            continue
        by_sender[sender].append(tx)
        by_pair[(sender, recipient)].append(tx)

    factors = {}
    for sender, outgoing in by_sender.items():
        distinct = len({tx["to_address"].lower() for tx in outgoing})
        if len(outgoing) >= MIN_BURST_TRANSFERS and distinct >= MIN_DISTINCT_RECIPIENTS:
            for tx in outgoing:
                factors.setdefault(tx["hash"], []).append({
                    "factor": "same_block_fan_out",
                    "points": 15,
                    "reason": "High-volume transfers to many recipients within one observed block",
                    "observed_transfer_count": len(outgoing),
                    "distinct_recipients": distinct,
                    "block_number": tx["block_number"],
                    "address": sender,
                })

    for (sender, recipient), transfers in by_pair.items():
        if len(transfers) >= MIN_REPEAT_TRANSFERS:
            for tx in transfers:
                factors.setdefault(tx["hash"], []).append({
                    "factor": "same_block_repeated_transfers",
                    "points": 10,
                    "reason": "Repeated transfers to the same recipient in one observed block",
                    "observed_transfer_count": len(transfers),
                    "block_number": tx["block_number"],
                    "from_address": sender,
                    "to_address": recipient,
                })
    return factors


def apply_behavior_risk(result, tx, behavior_factors):
    """Attach observed evidence; never override a confirmed sanctions score."""
    if result["score"] == 100:
        return result
    additions = behavior_factors.get(tx["hash"], [])
    if additions:
        result["factors"].extend(additions)
        result["score"] = min(100, result["score"] + sum(f["points"] for f in additions))
    return result
