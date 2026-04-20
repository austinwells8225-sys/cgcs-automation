"""Scheduler — runs periodic background jobs inside the FastAPI app.

Currently schedules the Smartsheet inbox poller. More jobs (daily digest,
reminders cron, etc.) can be registered here later.

The scheduler is wired into FastAPI's lifespan — it starts when the app
starts and shuts down cleanly on exit.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.smartsheet_inbox_poller import poll_smartsheet_inbox

logger = logging.getLogger(__name__)

# Config knobs — env vars let us tune without redeploying the code.
SMARTSHEET_POLL_MINUTES = int(os.getenv("SMARTSHEET_POLL_MINUTES", "5"))
SMARTSHEET_POLL_ENABLED = os.getenv("SMARTSHEET_POLL_ENABLED", "true").lower() == "true"
SMARTSHEET_POLL_MAX_EMAILS = int(os.getenv("SMARTSHEET_POLL_MAX_EMAILS", "10"))

_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler(compiled_graph) -> Optional[AsyncIOScheduler]:
    """Create and start the scheduler. Idempotent — safe to call twice."""
    global _scheduler
    if _scheduler is not None:
        logger.info("Scheduler already running")
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="America/Chicago")

    if SMARTSHEET_POLL_ENABLED:
        scheduler.add_job(
            _smartsheet_job,
            trigger="interval",
            minutes=SMARTSHEET_POLL_MINUTES,
            args=[compiled_graph],
            id="smartsheet_inbox_poll",
            name="Smartsheet inbox poll",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        logger.info(
            "Scheduled smartsheet_inbox_poll every %d minutes",
            SMARTSHEET_POLL_MINUTES,
        )
    else:
        logger.info("Smartsheet inbox polling DISABLED via env var")

    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started with %d job(s)", len(scheduler.get_jobs()))
    return scheduler


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly. Safe to call if never started."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
    except Exception:
        logger.exception("Error shutting down scheduler (non-fatal)")
    finally:
        _scheduler = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the running scheduler instance (for introspection / manual triggers)."""
    return _scheduler


async def _smartsheet_job(compiled_graph) -> None:
    """Wrapper around poll_smartsheet_inbox for APScheduler.

    Catches all exceptions so a failure never brings down the scheduler.
    """
    try:
        results = await poll_smartsheet_inbox(
            compiled_graph=compiled_graph,
            max_emails=SMARTSHEET_POLL_MAX_EMAILS,
        )
        logger.info(
            "Smartsheet poll: checked=%d processed=%d skipped=%d errors=%d",
            results.get("checked", 0),
            results.get("processed", 0),
            results.get("skipped", 0),
            len(results.get("errors", []) or []),
        )
    except Exception:
        logger.exception("Smartsheet poll job crashed (caught, scheduler keeps running)")
