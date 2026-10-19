"""Read-only audit of retained zero-native-value risk evidence.

Run with database configuration available:
    python -m scripts.audit_legacy_zero_value_scores

No UPDATE, DELETE, or score recomputation. Reports only retained evidence.
"""
import asyncio
import json

from src.database.connection import get_db, close_db


async def main():
    db = await get_db()
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            historical = await db.fetchrow("""
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
                    WITH recorded AS (
                        SELECT
                            t.value, t.risk_score, t.risk_factors,
                            COALESCE((
                                SELECT SUM(
                                    CASE WHEN (factor->>'points') ~ '^[0-9]+$'
                                        THEN (factor->>'points')::integer
                                        ELSE 0
                                    END
                                )
                                FROM jsonb_array_elements(
                                    CASE WHEN jsonb_typeof(t.risk_factors) = 'array'
                                        THEN t.risk_factors ELSE '[]'::jsonb END
                                ) AS factor
                            ), 0) AS factor_total
                        FROM transactions t
                        WHERE t.block_number BETWEEN $1 AND $2
                    )
                    SELECT
                        COUNT(*) AS recently_retained,
                        COUNT(*) FILTER (WHERE risk_factors IS NULL) AS missing_factors,
                        COUNT(*) FILTER (WHERE value = 0) AS recent_zero_value,
                        COUNT(*) FILTER (
                            WHERE value = 0 AND
                            risk_factors @> '[{"factor":"zero_value","points":5}]'::jsonb
                        ) AS old_five_point_rule_seen,
                        COUNT(*) FILTER (
                            WHERE value = 0 AND
                            risk_factors @> '[{"factor":"zero_value","points":0}]'::jsonb
                        ) AS corrected_zero_point_context_seen,
                        COUNT(*) FILTER (
                            WHERE risk_score IS DISTINCT FROM LEAST(100, factor_total)
                        ) AS score_factor_sum_mismatches
                    FROM recorded
                """, max(0, int(latest) - 9), int(latest))

        print(json.dumps({
            "scope": "one read-only snapshot of retained PostgreSQL transactions",
            "latest_retained_block": int(latest) if latest is not None else None,
            "recent_ten_block_audit": {
                key: int(value or 0) for key, value in dict(recent).items()
            } if recent is not None else None,
            **{key: int(value or 0) for key, value in dict(historical).items()},
            "disclaimer": "This audit does not rewrite scores; mismatches require transaction-level evidence review.",
        }, indent=2))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
