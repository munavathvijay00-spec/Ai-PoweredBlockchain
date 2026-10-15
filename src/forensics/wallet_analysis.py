"""Evidence-backed temporal graph analytics for investigated Ethereum wallets.

All findings are descriptive observations over cached provider evidence. They are not
fraud verdicts, ownership inference, taint propagation, or attribution. Asset amounts are
compared only within the same canonical asset key.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

ADDRESS_PREFIX = "0x"


def _address(value: Any) -> str | None:
    text = str(value or "").lower()
    return text if len(text) == 42 and text.startswith(ADDRESS_PREFIX) else None


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


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


def canonical_asset_key(row: dict[str, Any]) -> str:
    """Canonicalize assets without trusting non-unique token symbols."""
    category = str(row.get("category") or "").lower()
    contract = _address(row.get("contract_address"))
    if contract:
        return f"eip155:1/erc20:{contract}" if category == "erc20" else f"eip155:1/{category or 'token'}:{contract}"
    if category in {"external", "internal"}:
        return "eip155:1/native:ETH"
    symbol = str(row.get("asset") or "UNKNOWN").upper()
    return f"eip155:1/unverified-symbol:{symbol}"


def _evidence_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tx_hash": row.get("tx_hash"),
        "evidence_key": row.get("evidence_key"),
        "url": row.get("evidence_url"),
        "block_number": row.get("block_number"),
        "block_timestamp": row.get("block_timestamp"),
    }


def deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        key = (
            row.get("evidence_key"), row.get("tx_hash"), row.get("category"),
            row.get("from_address"), row.get("to_address"), row.get("contract_address"),
            row.get("token_id"), row.get("value_text"), row.get("block_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _emit(findings: list[dict[str, Any]], code: str, title: str, rows: list[dict[str, Any]], explanation: str, **details: Any) -> None:
    evidence = []
    seen = set()
    for row in rows:
        ref = _evidence_ref(row)
        stable = (ref.get("tx_hash"), ref.get("evidence_key"))
        if stable in seen:
            continue
        seen.add(stable)
        evidence.append(ref)
        if len(evidence) >= 20:
            break
    if not evidence:
        return
    findings.append({
        "code": code,
        "title": title,
        "status": "review",
        "explanation": explanation,
        "details": details,
        "evidence": evidence,
        "not_a_fraud_verdict": True,
    })


def analyze_wallet(root: str, rows: list[dict[str, Any]], rapid_minutes: int = 30) -> dict[str, Any]:
    root = root.lower()
    records = deduplicate(rows)
    valid = [
        row for row in records
        if _address(row.get("from_address")) and _address(row.get("to_address"))
    ]
    ordered = sorted(
        valid,
        key=lambda row: (
            _timestamp(row.get("block_timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            int(row.get("block_number") or 0),
            str(row.get("tx_hash") or ""),
        ),
    )

    findings: list[dict[str, Any]] = []
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        row["canonical_asset_key"] = canonical_asset_key(row)
        by_asset[row["canonical_asset_key"]].append(row)

    counterparties = set()
    outgoing = []
    incoming = []
    for row in ordered:
        source = _address(row.get("from_address"))
        target = _address(row.get("to_address"))
        if source == root:
            outgoing.append(row)
            if target != root:
                counterparties.add(target)
        if target == root:
            incoming.append(row)
            if source != root:
                counterparties.add(source)

    # Fan-out and fan-in are grouped by canonical asset so unlike token units never mix.
    for asset_key, group in by_asset.items():
        out_group = [row for row in group if _address(row.get("from_address")) == root]
        in_group = [row for row in group if _address(row.get("to_address")) == root]
        out_targets = {_address(row.get("to_address")) for row in out_group if _address(row.get("to_address")) != root}
        in_sources = {_address(row.get("from_address")) for row in in_group if _address(row.get("from_address")) != root}
        if len(out_targets) >= 3:
            _emit(
                findings, "fan_out", "Observed fan-out from investigated wallet", out_group,
                "The investigated wallet sent the same canonical asset to at least three distinct observed recipients.",
                asset_key=asset_key, unique_recipients=len(out_targets), transfer_count=len(out_group),
            )
        if len(in_sources) >= 3:
            _emit(
                findings, "fan_in", "Observed fan-in to investigated wallet", in_group,
                "The investigated wallet received the same canonical asset from at least three distinct observed senders.",
                asset_key=asset_key, unique_senders=len(in_sources), transfer_count=len(in_group),
            )

    # Rapid forwarding: receive then send same canonical asset soon afterwards. Values are
    # reported independently and never interpreted as taint or exact fund identity.
    rapid_seconds = max(1, rapid_minutes) * 60
    for asset_key, group in by_asset.items():
        receives = [row for row in group if _address(row.get("to_address")) == root and _timestamp(row.get("block_timestamp"))]
        sends = [row for row in group if _address(row.get("from_address")) == root and _timestamp(row.get("block_timestamp"))]
        pairs = []
        for received in receives:
            rt = _timestamp(received.get("block_timestamp"))
            for sent in sends:
                st = _timestamp(sent.get("block_timestamp"))
                delta = (st - rt).total_seconds()
                if 0 < delta <= rapid_seconds:
                    pairs.extend([received, sent])
                    break
        if pairs:
            _emit(
                findings, "rapid_forwarding", "Rapid same-asset forwarding observed", pairs,
                f"A receive event was followed by an outgoing event for the same canonical asset within {rapid_minutes} minutes.",
                asset_key=asset_key, window_minutes=rapid_minutes,
            )

    # Branch reconvergence uses observed two-hop cached evidence only: the root sends to two
    # or more distinct first-hop branches and those branches later send to one same address.
    first_hop = {_address(row.get("to_address")) for row in outgoing if _address(row.get("to_address")) != root}
    downstream: dict[tuple[str, str], set[str]] = defaultdict(set)
    downstream_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        source = _address(row.get("from_address"))
        target = _address(row.get("to_address"))
        if source in first_hop and target and target != root:
            key = (row["canonical_asset_key"], target)
            downstream[key].add(source)
            downstream_rows[key].append(row)
    for (asset_key, target), branches in downstream.items():
        if len(branches) >= 2:
            root_rows = [row for row in outgoing if _address(row.get("to_address")) in branches and row["canonical_asset_key"] == asset_key]
            _emit(
                findings, "branch_reconvergence", "Observed branch reconvergence", root_rows + downstream_rows[(asset_key, target)],
                "Two or more observed first-hop recipients later transferred the same canonical asset to one common downstream address.",
                asset_key=asset_key, branch_count=len(branches), downstream_address=target,
            )

    # Repeated-pair relationships can matter operationally, but remain descriptive.
    pair_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        pair_rows[(_address(row.get("from_address")), _address(row.get("to_address")), row["canonical_asset_key"])].append(row)
    for (source, target, asset_key), group in pair_rows.items():
        if len({row.get("tx_hash") for row in group if row.get("tx_hash")}) >= 3:
            _emit(
                findings, "repeated_pair", "Repeated observed transfer relationship", group,
                "At least three distinct observed transactions connect the same sender, recipient, and canonical asset.",
                source=source, target=target, asset_key=asset_key, transaction_count=len(group),
            )

    asset_counts = Counter(row["canonical_asset_key"] for row in ordered)
    return {
        "root": root,
        "record_count": len(ordered),
        "incoming_records": len(incoming),
        "outgoing_records": len(outgoing),
        "unique_counterparties": len(counterparties),
        "canonical_assets": [
            {"asset_key": key, "records": count}
            for key, count in asset_counts.most_common()
        ],
        "findings": findings,
        "finding_count": len(findings),
        "scope": "Observed cached provider evidence only; two-hop findings require overlapping cached evidence for the involved addresses.",
        "limitations": [
            "No finding proves ownership, intent, criminality, sanctions exposure, laundering, or taint.",
            "Amounts are never aggregated across different canonical assets.",
            "Provider transfer views are not complete EVM execution traces.",
            "Absence of a finding can result from incomplete pagination or cache coverage.",
        ],
    }
