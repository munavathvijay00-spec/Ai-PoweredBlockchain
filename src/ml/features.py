"""
Feature extraction for ML model.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict
from loguru import logger

from src.database.connection import get_db


class FeatureExtractor:
    FEATURE_COLUMNS = [
        "value_eth", "value_log", "value_zscore", "gas_price_gwei",
        "hour_of_day", "day_of_week",
        "from_tx_count", "to_tx_count",
        "from_unique_counterparties", "to_unique_counterparties",
        "from_age_days", "to_age_days",
        "is_contract_creation", "is_zero_value",
        "to_blacklisted", "from_blacklisted",
    ]

    def __init__(self):
        self.db = None

    async def _ensure_db(self):
        if self.db is None:
            self.db = await get_db()
        return self.db

    async def extract_for_training(self, limit: int = 50000) -> pd.DataFrame:
        db = await self._ensure_db()
        logger.info(f"Extracting features for up to {limit} transactions...")

        query = """
            WITH addr_stats AS (
                SELECT a.id, COUNT(t.id) AS tx_count
                FROM addresses a
                LEFT JOIN transactions t 
                    ON t.from_address_id = a.id OR t.to_address_id = a.id
                GROUP BY a.id
            ),
            counterparty_counts AS (
                SELECT from_address_id AS addr_id,
                       COUNT(DISTINCT to_address_id) AS unique_counterparties
                FROM transactions
                GROUP BY from_address_id
            )
            SELECT 
                t.id, t.hash, t.value, t.gas_price, t.timestamp, t.risk_score,
                t.from_address_id, t.to_address_id,
                af.address AS from_address, at.address AS to_address,
                af.first_seen AS from_first_seen, at.first_seen AS to_first_seen,
                COALESCE(cpc.unique_counterparties, 0) AS from_unique_counterparties,
                COALESCE(ast_from.tx_count, 0) AS from_tx_count,
                COALESCE(ast_to.tx_count, 0) AS to_tx_count
            FROM transactions t
            JOIN addresses af ON t.from_address_id = af.id
            LEFT JOIN addresses at ON t.to_address_id = at.id
            LEFT JOIN addr_stats ast_from ON ast_from.id = t.from_address_id
            LEFT JOIN addr_stats ast_to ON ast_to.id = t.to_address_id
            LEFT JOIN counterparty_counts cpc ON cpc.addr_id = t.from_address_id
            WHERE t.risk_score IS NOT NULL
            LIMIT $1
        """

        rows = await db.fetch(query, limit)
        logger.info(f"Fetched {len(rows)} transactions from DB")

        records = []
        for r in rows:
            features = self._build_features(r)
            features["risk_score"] = r["risk_score"]
            features["hash"] = r["hash"]
            records.append(features)

        df = pd.DataFrame(records)
        logger.info(f"Built dataframe with shape {df.shape}")
        return df

    def _build_features(self, row: Dict) -> Dict:
        value_wei = float(row.get("value", 0) or 0)
        value_eth = value_wei / 10**18

        timestamp = row.get("timestamp")
        if timestamp:
            try:
                hour = timestamp.hour
                dow = timestamp.weekday()
            except Exception:
                hour, dow = 0, 0
        else:
            hour, dow = 0, 0

        now = datetime.utcnow()
        from_age_days = 0
        to_age_days = 0
        if row.get("from_first_seen"):
            try:
                from_age_days = max(0, (now - row["from_first_seen"]).days)
            except Exception:
                pass
        if row.get("to_first_seen"):
            try:
                to_age_days = max(0, (now - row["to_first_seen"]).days)
            except Exception:
                pass

        value_log = np.log1p(value_eth)

        return {
            "value_eth": value_eth,
            "value_log": value_log,
            "value_zscore": 0.0,
            "gas_price_gwei": float(row.get("gas_price", 0) or 0) / 10**9,
            "hour_of_day": hour,
            "day_of_week": dow,
            "from_tx_count": int(row.get("from_tx_count", 0) or 0),
            "to_tx_count": int(row.get("to_tx_count", 0) or 0),
            "from_unique_counterparties": int(row.get("from_unique_counterparties", 0) or 0),
            "to_unique_counterparties": 0,
            "from_age_days": from_age_days,
            "to_age_days": to_age_days,
            "is_contract_creation": 0,
            "is_zero_value": 1 if value_eth == 0 else 0,
            "to_blacklisted": 0,
            "from_blacklisted": 0,
        }


_extractor = None


def get_extractor() -> FeatureExtractor:
    global _extractor
    if _extractor is None:
        _extractor = FeatureExtractor()
    return _extractor
