"""Persist reproducible investigation package metadata and payloads."""
from __future__ import annotations

import json
from typing import Any


async def ensure_run_schema(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS investigation_runs (
            id BIGSERIAL PRIMARY KEY,
            case_id TEXT NOT NULL,
            address VARCHAR(42) NOT NULL,
            package_sha256 VARCHAR(64) NOT NULL,
            judge_demo_ready BOOLEAN NOT NULL,
            blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            finding_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
            ai_status TEXT,
            selected_category_history_complete BOOLEAN NOT NULL DEFAULT FALSE,
            package JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(case_id, package_sha256)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_investigation_runs_case_created
        ON investigation_runs(case_id, created_at DESC)
        """
    )


async def save_run(db, case_id: str, package: dict[str, Any]) -> dict[str, Any]:
    await ensure_run_schema(db)
    manifest = package.get("manifest") or {}
    readiness = package.get("readiness") or {}
    sections = package.get("sections") or {}
    forensics = sections.get("forensics") or {}
    coverage = sections.get("coverage") or {}
    ai = sections.get("ai_investigation") or {}
    evidence = sections.get("evidence") or []
    finding_codes = sorted({str(item.get("code")) for item in (forensics.get("findings") or []) if item.get("code")})
    package_hash = str(manifest.get("package_sha256") or "")
    if len(package_hash) != 64:
        raise ValueError("Investigation package is missing a valid SHA-256 manifest")
    run_id = await db.fetchval(
        """
        INSERT INTO investigation_runs (
            case_id,address,package_sha256,judge_demo_ready,blockers,
            evidence_count,finding_codes,ai_status,
            selected_category_history_complete,package
        ) VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7::jsonb,$8,$9,$10::jsonb)
        ON CONFLICT (case_id,package_sha256) DO UPDATE SET
            judge_demo_ready=EXCLUDED.judge_demo_ready,
            blockers=EXCLUDED.blockers,
            evidence_count=EXCLUDED.evidence_count,
            finding_codes=EXCLUDED.finding_codes,
            ai_status=EXCLUDED.ai_status,
            selected_category_history_complete=EXCLUDED.selected_category_history_complete,
            package=EXCLUDED.package,
            created_at=NOW()
        RETURNING id
        """,
        case_id,
        str(package.get("address") or "").lower(),
        package_hash,
        bool(readiness.get("judge_demo_ready")),
        json.dumps(readiness.get("blockers") or []),
        len(evidence),
        json.dumps(finding_codes),
        ai.get("status"),
        bool(coverage.get("selected_category_history_complete")),
        json.dumps(package, default=str),
    )
    return {
        "run_id": int(run_id),
        "package_sha256": package_hash,
        "judge_demo_ready": bool(readiness.get("judge_demo_ready")),
        "blockers": readiness.get("blockers") or [],
        "evidence_count": len(evidence),
        "finding_count": int(forensics.get("finding_count") or 0),
        "finding_codes": finding_codes,
        "ai_status": ai.get("status"),
        "ai_used": bool(ai.get("ai_used")),
        "ai_grounded": bool(ai.get("grounded", True)),
        "selected_category_history_complete": bool(coverage.get("selected_category_history_complete")),
        "rows_exported": int(coverage.get("rows_exported") or 0),
        "query_truncated": bool(coverage.get("query_truncated")),
        "oldest_block_cached": coverage.get("oldest_block_cached"),
        "newest_block_cached": coverage.get("newest_block_cached"),
    }


async def latest_run(db, case_id: str) -> dict[str, Any] | None:
    await ensure_run_schema(db)
    row = await db.fetchrow(
        """
        SELECT id,case_id,address,package_sha256,judge_demo_ready,blockers,
               evidence_count,finding_codes,ai_status,
               selected_category_history_complete,created_at
        FROM investigation_runs
        WHERE case_id=$1
        ORDER BY created_at DESC,id DESC
        LIMIT 1
        """,
        case_id,
    )
    return dict(row) if row else None
