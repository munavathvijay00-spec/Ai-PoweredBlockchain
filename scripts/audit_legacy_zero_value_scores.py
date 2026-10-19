"""Read-only audit of retained zero-native-value risk scoring.

Run inside a configured Railway service:
    python scripts/audit_legacy_zero_value_scores.py

Never rewrites historical risk scores or factors. A prior score may contain
other valid signals; subtracting five points without full original evidence
would create inaccurate investigations.
"""
import asyncio
import json

from src.database.connection import get_db, close_db


async def main():
    db = await get_db()
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            row = await db.fetchrow("""
                SELECT
                  COUNT(*) AS retained_transactions,
                  COUNT(*) FILTER (WHERE value = 0) AS zero_value_transactions,
                  COUNT(*) FILTER (
                    WHERE value = 0
                      AND risk_factors @> '[{"factor":"zero_value","points":5}]'::jsonb
                  ) AS historical_zero_value_five_point_factors,
                  COUNT(*) FILTER (
                    WHERE value = 0 AND risk_score >= 20
                      AND risk_factors @> '[{"factor":"zero_value","points":5}]'::jsonb
                  ) AS historical_zero_value_review_rows
                FROM transactions
            """)
            latest = await db.fetchval("SELECT MAX(block_number) FROM transactions")
            recent = None
            if latest is not None:
                recent = await db.fetchrow("""
                    SELECT COUNT(*) AS recently_retained,
                           COUNT(*) FILTER (WHERE risk_factors IS NULL) AS missing_factors,
                           COUNT(*) FILTER (WHERE value = 0) AS recent_zero_value,
                           COUNT(*) FILTER (
                               WHERE value = 0
                                 AND risk_factors @> '[{"factor":"zero_value","points":5}]'::jsonb
                           ) AS old_five_point_rule_seen,
                           COUNT(*) FILTER (
                               WHERE value = 0
                                 AND risk_factors @> '[{"factor":"zero_value","points":0}]'::jsonb
                           ) AS corrected_zero_point_context_seen,
                           COUNT(*) FILTER (
                               WHERE risk_score <> LEAST(100, (
                                 SELECT COALESCE(SUM(
                                   CASE WHEN (factor->>'points') ~ '^[0-9]+
            "scope": "retained PostgreSQL transactions at one read-only snapshot",
            "latest_retained_block": latest,
            "recent_ten_block_audit": {key: int(value or 0) for key, value in dict(recent).items()} if recent else None,
            **{key: int(value or 0) for key, value in dict(row).items()},
            "disclaimer": "Historical scores are unchanged. Existing points cannot be safely subtracted without reconstructing original scoring evidence.",
        }, indent=2))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())

                                     THEN (factor->>'points')::int ELSE 0 END
                                 ), 0)
                                 FROM jsonb_array_elements(
                                   CASE WHEN jsonb_typeof(t.risk_factors) = 'array'
                                     THEN t.risk_factors ELSE '[]'::jsonb END
                                 ) AS factor
                               ))
                           ) AS score_factor_sum_mismatches
                    FROM transactions AS t
                    WHERE block_number BETWEEN $1 AND $2
                """, max(0, int(latest) - 9), latest)
        print(json.dumps({
            "scope": "retained PostgreSQL transactions at one read-only snapshot",
            **{key: int(value or 0) for key, value in dict(row).items()},
            "disclaimer": "Historical scores are unchanged. Existing points cannot be safely subtracted without reconstructing original scoring evidence.",
        }, indent=2))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
