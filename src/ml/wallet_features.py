"""Blockchain-native behavioral feature extraction for investigated wallets.

Features are descriptive and label-independent. They can support future supervised models,
anomaly detection, and model audits without importing ChainScope risk scores or entity
labels into the feature vector.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from statistics import median
from typing import Any

from src.forensics.wallet_analysis import canonical_asset_key, deduplicate


def _address(value: Any) -> str | None:
    text = str(value or "").lower()
    return text if len(text) == 42 and text.startswith("0x") else None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def extract_wallet_features(root: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    root = root.lower()
    records = deduplicate(rows)
    valid = [row for row in records if _address(row.get("from_address")) and _address(row.get("to_address"))]
    incoming = [row for row in valid if _address(row.get("to_address")) == root]
    outgoing = [row for row in valid if _address(row.get("from_address")) == root]
    counterparties = []
    outgoing_targets = []
    incoming_sources = []
    self_transfers = 0
    for row in valid:
        source = _address(row.get("from_address"))
        target = _address(row.get("to_address"))
        if source == root and target == root:
            self_transfers += 1
        elif source == root and target:
            counterparties.append(target)
            outgoing_targets.append(target)
        elif target == root and source:
            counterparties.append(source)
            incoming_sources.append(source)

    timestamps = sorted(ts for ts in (_timestamp(row.get("block_timestamp")) for row in valid) if ts)
    gaps = [
        (current - previous).total_seconds()
        for previous, current in zip(timestamps, timestamps[1:])
        if current >= previous
    ]
    mean_gap = (sum(gaps) / len(gaps)) if gaps else 0.0
    variance = (sum((gap - mean_gap) ** 2 for gap in gaps) / len(gaps)) if gaps else 0.0
    std_gap = math.sqrt(variance)
    burstiness_cv = (std_gap / mean_gap) if mean_gap > 0 else 0.0
    active_span_hours = ((timestamps[-1] - timestamps[0]).total_seconds() / 3600.0) if len(timestamps) >= 2 else 0.0

    cp_counts = Counter(counterparties)
    repeated_cp_records = sum(count for count in cp_counts.values() if count >= 2)
    total_root_records = len(incoming) + len(outgoing)
    repeated_cp_ratio = (repeated_cp_records / total_root_records) if total_root_records else 0.0

    canonical_assets = {canonical_asset_key(row) for row in valid}
    contract_categories = {"erc20", "erc721", "erc1155", "internal"}
    contract_like = sum(1 for row in valid if str(row.get("category") or "").lower() in contract_categories)
    contract_fraction = (contract_like / len(valid)) if valid else 0.0

    incoming_count = len(incoming)
    outgoing_count = len(outgoing)
    direction_total = incoming_count + outgoing_count
    outgoing_ratio = (outgoing_count / direction_total) if direction_total else 0.0
    incoming_ratio = (incoming_count / direction_total) if direction_total else 0.0

    return {
        "schema_version": 1,
        "root": root,
        "evidence_records": len(valid),
        "features": {
            "incoming_count": incoming_count,
            "outgoing_count": outgoing_count,
            "incoming_ratio": round(incoming_ratio, 6),
            "outgoing_ratio": round(outgoing_ratio, 6),
            "unique_counterparties": len(set(counterparties)),
            "unique_incoming_sources": len(set(incoming_sources)),
            "unique_outgoing_targets": len(set(outgoing_targets)),
            "counterparty_diversity_ratio": round((len(set(counterparties)) / total_root_records) if total_root_records else 0.0, 6),
            "repeated_counterparty_ratio": round(repeated_cp_ratio, 6),
            "self_transfer_count": self_transfers,
            "canonical_asset_diversity": len(canonical_assets),
            "contract_or_token_record_fraction": round(contract_fraction, 6),
            "active_span_hours": round(active_span_hours, 6),
            "median_interarrival_seconds": round(float(median(gaps)), 6) if gaps else 0.0,
            "mean_interarrival_seconds": round(mean_gap, 6),
            "interarrival_burstiness_cv": round(burstiness_cv, 6),
        },
        "feature_policy": {
            "uses_risk_score": False,
            "uses_entity_labels": False,
            "uses_ai_output": False,
            "mixes_asset_values": False,
        },
        "scope": "Features describe only the cached provider evidence supplied to this extractor.",
    }
