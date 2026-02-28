"""Shared utilities for all graph nodes: LLM client, retry logic, sanitization."""

from __future__ import annotations

import json
import logging
import re
import time

from langchain_anthropic import ChatAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model=settings.claude_model,
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    timeout=settings.llm_timeout,
)


def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM response, handling markdown code blocks."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1)
    return json.loads(text.strip())


def _invoke_with_retry(messages: list[dict]) -> str:
    """Invoke LLM with exponential backoff retry on transient failures."""
    last_error = None
    for attempt in range(settings.llm_max_retries):
        try:
            response = llm.invoke(messages)
            return response.content
        except Exception as e:
            last_error = e
            if attempt < settings.llm_max_retries - 1:
                delay = settings.llm_retry_base_delay * (2 ** attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, settings.llm_max_retries, delay, e,
                )
                time.sleep(delay)
            else:
                logger.error("LLM call failed after %d attempts: %s", settings.llm_max_retries, e)
    raise last_error


def _sanitize_string(value: str | None) -> str:
    """Strip control characters and excessive whitespace from input strings."""
    if not value:
        return ""
    # Remove control characters except newlines and tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    # Collapse excessive whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    # Limit length to prevent abuse
    return cleaned[:5000].strip()
