"""Read-only smoke test for the Gmail auth path.

Reads up to N recent Smartsheet-pattern notifications from the configured
GMAIL_DELEGATED_USER inbox and prints them. No side effects — does NOT
mark messages as read, send mail, or create drafts.

Use this to verify DWD authorization is working against the live trigger
inbox after ACC Workspace admin authorizes the service account for the
@austincc.edu domain.

Usage:
    cd /Users/a2068129/Desktop/ai-intake
    source langgraph-agent/.venv/bin/activate  # or your venv path
    python scripts/test_gmail_read.py
    python scripts/test_gmail_read.py --max 20
    python scripts/test_gmail_read.py --query "is:unread"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the langgraph-agent package importable when running from repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "langgraph-agent"))

from app.config import settings  # noqa: E402
from app.services import gmail_service  # noqa: E402
from app.services.smartsheet_inbox_poller import SMARTSHEET_QUERY  # noqa: E402


async def main(query: str, max_results: int) -> int:
    print(f"GMAIL_DELEGATED_USER = {settings.gmail_delegated_user}")
    print(f"Query                = {query}")
    print(f"Max results          = {max_results}")
    print("-" * 72)

    try:
        emails = await gmail_service.read_inbox(query=query, max_results=max_results)
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        print()
        print("Common causes:")
        print("  - Service account client_id not authorized for DWD on the")
        print("    target Workspace domain (unauthorized_client error)")
        print("  - GOOGLE_SERVICE_ACCOUNT_FILE missing or unreadable")
        print("  - GMAIL_DELEGATED_USER mailbox does not exist in the domain")
        return 1

    if not emails:
        print("OK auth — but inbox returned 0 matches.")
        print()
        print("If you expected Smartsheet notifications and got zero:")
        print("  - Confirm the Smartsheet form is actually sending to this mailbox")
        print("  - Check the query — try '--query is:unread' to see ANY unread mail")
        print("  - Confirm GMAIL_DELEGATED_USER points at the right inbox")
        return 0

    print(f"OK — found {len(emails)} matching messages.\n")
    for i, email in enumerate(emails, start=1):
        print(f"[{i}] id={email.get('id', '')}")
        print(f"    from:    {email.get('from', '')}")
        print(f"    to:      {email.get('to', '')}")
        print(f"    subject: {email.get('subject', '')}")
        print(f"    date:    {email.get('date', '')}")
        print()

    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only Gmail smoke test.")
    p.add_argument(
        "--query",
        default=SMARTSHEET_QUERY,
        help="Gmail search query (default: the SMARTSHEET_QUERY used by the poller)",
    )
    p.add_argument(
        "--max",
        type=int,
        default=5,
        help="Maximum messages to return (default: 5)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args.query, args.max)))
