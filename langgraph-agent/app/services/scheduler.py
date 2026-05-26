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

from app.services.calendar_sync import sync_range as calendar_sync_range
from app.services.smartsheet_inbox_poller import poll_smartsheet_inbox

logger = logging.getLogger(__name__)

# Config knobs — env vars let us tune without redeploying the code.
SMARTSHEET_POLL_MINUTES = int(os.getenv("SMARTSHEET_POLL_MINUTES", "5"))
SMARTSHEET_POLL_ENABLED = os.getenv("SMARTSHEET_POLL_ENABLED", "true").lower() == "true"
SMARTSHEET_POLL_MAX_EMAILS = int(os.getenv("SMARTSHEET_POLL_MAX_EMAILS", "10"))

CALENDAR_SYNC_MINUTES = int(os.getenv("CALENDAR_SYNC_MINUTES", "5"))
CALENDAR_SYNC_ENABLED = os.getenv("CALENDAR_SYNC_ENABLED", "true").lower() == "true"
CALENDAR_SYNC_BACK_DAYS = int(os.getenv("CALENDAR_SYNC_BACK_DAYS", "30"))
CALENDAR_SYNC_FWD_DAYS = int(os.getenv("CALENDAR_SYNC_FWD_DAYS", "90"))

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

    if CALENDAR_SYNC_ENABLED:
        scheduler.add_job(
            _calendar_sync_job,
            trigger="interval",
            minutes=CALENDAR_SYNC_MINUTES,
            id="calendar_sync",
            name="Google Calendar -> reservations sync",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled calendar_sync every %d minutes", CALENDAR_SYNC_MINUTES)
    else:
        logger.info("Calendar sync DISABLED via env var")

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


async def _calendar_sync_job() -> None:
    """Sync the rolling calendar window. Catches everything so the scheduler stays up."""
    from datetime import date, timedelta
    try:
        today = date.today()
        start = (today - timedelta(days=CALENDAR_SYNC_BACK_DAYS)).isoformat()
        end = (today + timedelta(days=CALENDAR_SYNC_FWD_DAYS)).isoformat()
        result = await calendar_sync_range(start, end)
        logger.info(
            "Calendar sync: fetched=%d inserted=%d dedup=%d other=%d errors=%d",
            result.get("fetched", 0), result.get("inserted", 0),
            result.get("skipped_dedup", 0), result.get("skipped_other", 0),
            len(result.get("errors", []) or []),
        )
    except Exception:
        logger.exception("Calendar sync job crashed (caught, scheduler keeps running)")


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
