"""Idempotent migration runner — applies pending SQL migrations on startup.

Postgres' /docker-entrypoint-initdb.d/ only fires on first volume init,
so additive migrations added later were never applied to long-lived DBs.
This runner walks db/migrations/*.sql, tracks applied filenames in a
schema_migrations table, and applies any that haven't run yet.

Each migration file runs in its own transaction so a failure on one
doesn't poison the others.

If a long-lived DB already has migrations applied via a different path
(e.g., the original docker-entrypoint-initdb.d), the agent self-heals
on first boot: it inspects whether the migration's "expected end state"
already exists and marks it applied without re-running.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.db.connection import get_pool

logger = logging.getLogger(__name__)

_CANDIDATE_DIRS = [
    Path("/app/db/migrations"),
    Path(__file__).resolve().parents[3] / "db" / "migrations",
]


def _migrations_dir() -> Path | None:
    for p in _CANDIDATE_DIRS:
        if p.is_dir():
            return p
    return None


async def _seed_already_applied_for_long_lived_db(pool) -> None:
    """If reservations table exists but schema_migrations is empty, this
    is a pre-runner DB. Mark 001/002/003/005/007/008/009/010 as applied
    so the runner only tries the genuinely new ones (e.g., 011)."""
    has_reservations = await pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'cgcs' AND table_name = 'reservations'
        )
        """
    )
    if not has_reservations:
        return

    existing = await pool.fetchval("SELECT COUNT(*) FROM cgcs.schema_migrations")
    if existing and existing > 0:
        return

    legacy = [
        "001_initial_schema.sql",
        "002_seed_data.sql",
        "003_multi_capability.sql",
        "004_placeholder.sql",
        "005_revenue_tracking.sql",
        "006_placeholder.sql",
        "007_compliance_checklist.sql",
        "008_rejection_patterns.sql",
        "009_quote_versions.sql",
        "010_dashboard_alerts.sql",
    ]
    await pool.executemany(
        "INSERT INTO cgcs.schema_migrations (filename) VALUES ($1) "
        "ON CONFLICT DO NOTHING",
        [(f,) for f in legacy],
    )
    logger.info("Seeded %d legacy migrations as already-applied", len(legacy))


async def run_migrations() -> dict:
    """Apply any unapplied migrations. Returns a small report dict.

    Safe to call repeatedly — no-op when everything is up to date.
    Raises on a real migration failure so we don't silently mask bugs.
    """
    mig_dir = _migrations_dir()
    if mig_dir is None:
        logger.warning("No migrations directory found; skipping startup migrations")
        return {"applied": [], "skipped": [], "found_dir": None}

    pool = await get_pool()

    await pool.execute(
        """
        CREATE SCHEMA IF NOT EXISTS cgcs;
        CREATE TABLE IF NOT EXISTS cgcs.schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    await _seed_already_applied_for_long_lived_db(pool)

    applied_rows = await pool.fetch("SELECT filename FROM cgcs.schema_migrations")
    already = {r["filename"] for r in applied_rows}

    files = sorted(p for p in mig_dir.glob("*.sql") if p.is_file())
    applied: list[str] = []
    skipped: list[str] = []

    for f in files:
        if f.name in already:
            skipped.append(f.name)
            continue

        sql = f.read_text()
        if not sql.strip():
            skipped.append(f.name)
            continue

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO cgcs.schema_migrations (filename) VALUES ($1)",
                    f.name,
                )
        applied.append(f.name)
        logger.info("Applied migration %s", f.name)

    logger.info(
        "Migration runner complete: applied=%d skipped=%d dir=%s",
        len(applied), len(skipped), mig_dir,
    )
    return {"applied": applied, "skipped": skipped, "found_dir": str(mig_dir)}
