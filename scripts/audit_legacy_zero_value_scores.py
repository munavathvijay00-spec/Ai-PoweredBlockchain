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
        print(json.dumps({
            "scope": "retained PostgreSQL transactions at one read-only snapshot",
            **{key: int(value or 0) for key, value in dict(row).items()},
            "disclaimer": "Historical scores are unchanged. Existing points cannot be safely subtracted without reconstructing original scoring evidence.",
        }, indent=2))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
