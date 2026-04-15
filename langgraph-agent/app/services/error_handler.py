"""Error classification and handling for the CGCS pipeline.

Classifies errors as retryable or fatal, and builds alert payloads.
"""

from __future__ import annotations

# Retryable error types — these are transient and should be retried
_RETRYABLE_PATTERNS = [
    "timeout",
    "rate limit",
    "ratelimit",
    "429",
    "503",
    "502",
    "504",
    "connection reset",
    "connection refused",
    "temporary failure",
    "service unavailable",
    "too many requests",
    "ssl",
    "eof",
]

# Fatal error types — these won't be fixed by retrying
_FATAL_PATTERNS = [
    "invalid",
    "missing required",
    "not found",
    "401",
    "403",
    "422",
    "validation",
    "parse error",
    "key error",
    "type error",
    "value error",
]


def classify_error(error: Exception | str) -> dict:
    """Classify an error as retryable or fatal.

    Returns:
        {
            "error_type": "retryable" | "fatal",
            "error_class": str,
            "error_message": str,
            "should_dlq": bool,
            "should_alert": bool,
        }
    """
    msg = str(error).lower()
    error_class = type(error).__name__ if isinstance(error, Exception) else "str"

    for pattern in _RETRYABLE_PATTERNS:
        if pattern in msg:
            return {
                "error_type": "retryable",
                "error_class": error_class,
                "error_message": str(error),
                "should_dlq": False,
                "should_alert": False,
            }

    return {
        "error_type": "fatal",
        "error_class": error_class,
        "error_message": str(error),
        "should_dlq": True,
        "should_alert": True,
    }


def build_error_alert(
    error: Exception | str,
    context: str,
    request_id: str | None = None,
) -> dict:
    """Build a dashboard alert dict for a fatal error.

    Returns:
        {"reservation_id": str|None, "alert_type": str, "title": str, "detail": str}
    """
    classification = classify_error(error)
    return {
        "reservation_id": request_id,
        "alert_type": "pipeline_error",
        "title": f"Pipeline Error: {context}",
        "detail": f"[{classification['error_class']}] {classification['error_message']}",
    }
