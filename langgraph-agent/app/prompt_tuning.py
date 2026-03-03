"""Prompt tuning — fetch rejection lessons to improve future email drafts."""

from __future__ import annotations

import logging

from app.db.rejection_queries import get_rejection_patterns

logger = logging.getLogger(__name__)


async def get_rejection_lessons(
    category: str | None = None,
    limit: int = 5,
) -> str:
    """Build a lessons string from recent rejection patterns.

    Returns an empty string if no patterns exist or on any error,
    so this never blocks email drafting.
    """
    try:
        patterns = await get_rejection_patterns(category=category, limit=limit)
    except Exception:
        logger.debug("Failed to fetch rejection patterns for lessons", exc_info=True)
        return ""

    if not patterns:
        return ""

    lines = [
        "## Past Rejection Lessons",
        "When drafting replies, avoid these previously rejected patterns:",
    ]

    for i, p in enumerate(patterns, 1):
        reason = p.get("rejection_reason", "Unknown reason")
        selected_idx = p.get("selected_revision_index")
        final = p.get("final_draft")

        if selected_idx is not None and final:
            lines.append(
                f"{i}. Rejection: \"{reason}\" — Admin chose revision #{selected_idx + 1}."
            )
        elif final:
            lines.append(
                f"{i}. Rejection: \"{reason}\" — Admin wrote a custom replacement."
            )
        else:
            lines.append(
                f"{i}. Rejection: \"{reason}\" — No resolution selected yet."
            )

    return "\n".join(lines)
