"""Reply processor — handles ongoing email conversations with requesters.

Edit loop management, escalation detection, furniture change detection,
and AV/catering change alert creation.
"""

from __future__ import annotations

import re

from app.cgcs_constants import (
    ESCALATION_RECIPIENTS,
    MOVING_TEAM,
    MOVING_TEAM_CC,
    CGCS_SYSTEM_EMAIL,
)
from app.services.intake_processor import (
    _format_event_date,
    _format_room_display,
)

EDIT_LOOP_MAX = 10
EDIT_LOOP_LIMIT_MESSAGE = (
    "We've reached the limit of changes we can process through this channel. "
    "Please contact us directly at admin@cgcs-acc.org or call (512) 983-3679 "
    "to finalize your event details."
)

ESCALATION_AUTO_REPLY = (
    "I've forwarded your request to our team for personal attention. "
    "Someone will be in touch with you directly within 24 hours."
)

# ============================================================
# Edit Loop
# ============================================================


def check_edit_loop(edit_loop_count: int) -> dict:
    """Check if the edit loop limit has been reached.

    Returns:
        {
            "edit_loop_count": int (incremented),
            "limit_reached": bool,
            "limit_message": str | None,
        }
    """
    new_count = edit_loop_count + 1
    if new_count >= EDIT_LOOP_MAX:
        return {
            "edit_loop_count": new_count,
            "limit_reached": True,
            "limit_message": EDIT_LOOP_LIMIT_MESSAGE,
        }
    return {
        "edit_loop_count": new_count,
        "limit_reached": False,
        "limit_message": None,
    }


# ============================================================
# Escalation Detection
# ============================================================

_HUMAN_REQUEST_PATTERNS = [
    r"(?:i\s+)?want\s+to\s+(?:speak|talk)\s+to\s+(?:a\s+)?(?:someone|person|human|manager|supervisor)",
    r"can\s+i\s+(?:speak|talk)\s+(?:to|with)\s+(?:a\s+)?(?:person|someone|human|manager)",
    r"(?:let|have)\s+me\s+(?:speak|talk)\s+to\s+(?:a\s+)?(?:person|someone|human)",
    r"need\s+(?:to\s+)?(?:speak|talk)\s+(?:to|with)\s+(?:a\s+)?(?:real\s+)?(?:person|someone|human)",
    r"transfer\s+me\s+to\s+(?:a\s+)?(?:person|someone|human)",
    r"is\s+there\s+(?:a\s+)?(?:person|someone|human)\s+i\s+can\s+(?:talk|speak)\s+to",
    r"connect\s+me\s+(?:to|with)\s+(?:a\s+)?(?:person|someone|human)",
]

_FRUSTRATION_PATTERNS = [
    r"this\s+is\s+(?:ridiculous|unacceptable|absurd|insane|crazy|outrageous)",
    r"nobody\s+is\s+(?:helping|responding|listening)",
    r"no\s+one\s+is\s+(?:helping|responding|listening)",
    r"i['\u2019]ve\s+been\s+waiting",
    r"(?:extremely|very|so)\s+(?:frustrated|disappointed|upset|unhappy)",
    r"worst\s+(?:experience|service)",
    r"how\s+(?:many|long)\s+(?:times|more)\s+do\s+i\s+(?:have|need)\s+to",
    r"getting\s+(?:nowhere|the\s+runaround)",
    r"waste\s+(?:of\s+)?(?:my\s+)?time",
]


def detect_escalation(
    reply_body: str,
    failed_replies: int = 0,
) -> dict:
    """Detect if a client reply requires escalation.

    Args:
        reply_body: The client's reply email text.
        failed_replies: Number of back-and-forth without resolution.

    Returns:
        {
            "escalation_needed": bool,
            "reasons": list[str],
            "auto_reply": str | None,
            "forward_to": list[str] | None,
        }
    """
    reasons: list[str] = []
    text = reply_body.lower()

    for pattern in _HUMAN_REQUEST_PATTERNS:
        if re.search(pattern, text):
            reasons.append("Client explicitly requested a human")
            break

    for pattern in _FRUSTRATION_PATTERNS:
        if re.search(pattern, text):
            reasons.append("Frustration language detected")
            break

    if failed_replies >= 3:
        reasons.append(f"Conversation has {failed_replies} failed replies without resolution")

    if reasons:
        return {
            "escalation_needed": True,
            "reasons": reasons,
            "auto_reply": ESCALATION_AUTO_REPLY,
            "forward_to": list(ESCALATION_RECIPIENTS),
        }

    return {
        "escalation_needed": False,
        "reasons": [],
        "auto_reply": None,
        "forward_to": None,
    }


# ============================================================
# Furniture Change Detection
# ============================================================

_FURNITURE_KEYWORDS = [
    "table", "tables", "chair", "chairs", "stage", "podium", "podiums",
    "linen", "linens", "furniture", "round table", "round tables",
    "setup", "seating",
]

_FURNITURE_CHANGE_PATTERNS = [
    r"(?:now\s+)?need\s+(\d+)\s+(\w[\w\s]*?)(?:\s+instead)",
    r"(?:can\s+we\s+)?add\s+(?:a\s+)?(\w[\w\s]*?)(?:\?|\.|\s|$)",
    r"(?:don['\u2019]t|do\s+not)\s+need\s+(?:the\s+)?(\w[\w\s]*?)(?:\s+anymore)?",
    r"(?:remove|cancel|drop)\s+(?:the\s+)?(\w[\w\s]*)",
    r"(?:change|update|modify)\s+(?:the\s+)?(?:furniture|tables?|chairs?|setup)",
    r"(\d+)\s+(\w[\w\s]*?)\s+instead\s+of\s+(\d+)",
]


def detect_furniture_changes(reply_body: str) -> dict:
    """Detect if a reply contains furniture change requests.

    Returns:
        {
            "furniture_changes_detected": bool,
            "change_descriptions": list[str],
            "raw_text": str (relevant excerpt),
        }
    """
    text_lower = reply_body.lower()

    has_furniture_keyword = any(kw in text_lower for kw in _FURNITURE_KEYWORDS)
    if not has_furniture_keyword:
        return {
            "furniture_changes_detected": False,
            "change_descriptions": [],
            "raw_text": "",
        }

    descriptions: list[str] = []
    for pattern in _FURNITURE_CHANGE_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for m in matches:
            descriptions.append(m.group(0).strip())

    if not descriptions:
        # Keyword present but no specific change pattern — check for
        # quantity + furniture keyword combos
        qty_matches = re.findall(r"(\d+)\s+(" + "|".join(_FURNITURE_KEYWORDS) + r")", text_lower)
        for qty, item in qty_matches:
            descriptions.append(f"{qty} {item}")

    if not descriptions:
        # Check for modifier words near furniture keywords
        modifier_pattern = r"(?:different|new|change|swap|replace|switch|alternate)\s+(?:\w+\s+)?(" + "|".join(_FURNITURE_KEYWORDS) + r")"
        mod_matches = re.findall(modifier_pattern, text_lower)
        for item in mod_matches:
            descriptions.append(f"change {item}")

    if descriptions:
        return {
            "furniture_changes_detected": True,
            "change_descriptions": descriptions,
            "raw_text": reply_body[:500],
        }

    return {
        "furniture_changes_detected": False,
        "change_descriptions": [],
        "raw_text": "",
    }


def draft_furniture_update_email(
    parsed: dict,
    change_descriptions: list[str],
) -> dict:
    """Draft an updated furniture coordination email showing what changed.

    Returns:
        {"to": str, "cc": str, "subject": str, "body": str}
    """
    event_name = parsed.get("event_name") or "Unnamed Event"
    event_date = _format_event_date(parsed.get("event_start_date"))
    room = _format_room_display(parsed.get("event_room"))

    changes_text = "\n".join(f"- {d}" for d in change_descriptions)

    to = ", ".join(MOVING_TEAM)
    cc = MOVING_TEAM_CC
    subject = f"UPDATED Furniture Request \u2014 {event_name} on {event_date}"

    body = (
        f"Hi Tyler and Scott,\n"
        f"\n"
        f"The requester has updated furniture needs for an upcoming event:\n"
        f"\n"
        f"Event: {event_name}\n"
        f"Date: {event_date}\n"
        f"Room: {room}\n"
        f"\n"
        f"Changes requested:\n"
        f"{changes_text}\n"
        f"\n"
        f"Please confirm the updated setup.\n"
        f"\n"
        f"Thank you,\n"
        f"CGCS Team"
    )

    return {"to": to, "cc": cc, "subject": subject, "body": body}


# ============================================================
# AV / Catering Change Detection
# ============================================================

_AV_KEYWORDS = [
    "projector", "projection", "microphone", "mic", "speaker", "speakers",
    "audio", "video", "av ", "a/v", "sound", "screen", "webcast",
    "recording", "streaming",
]

_CATERING_KEYWORDS = [
    "catering", "food", "beverage", "drinks", "lunch", "breakfast",
    "dinner", "coffee", "snacks", "menu", "meal",
]


def detect_av_catering_changes(reply_body: str) -> dict:
    """Detect if a reply mentions AV or catering changes.

    Returns:
        {
            "av_change_detected": bool,
            "catering_change_detected": bool,
            "av_excerpt": str,
            "catering_excerpt": str,
        }
    """
    text_lower = reply_body.lower()

    av_detected = any(kw in text_lower for kw in _AV_KEYWORDS)
    catering_detected = any(kw in text_lower for kw in _CATERING_KEYWORDS)

    av_excerpt = ""
    catering_excerpt = ""

    if av_detected:
        for kw in _AV_KEYWORDS:
            idx = text_lower.find(kw)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(reply_body), idx + len(kw) + 100)
                av_excerpt = reply_body[start:end].strip()
                break

    if catering_detected:
        for kw in _CATERING_KEYWORDS:
            idx = text_lower.find(kw)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(reply_body), idx + len(kw) + 100)
                catering_excerpt = reply_body[start:end].strip()
                break

    return {
        "av_change_detected": av_detected,
        "catering_change_detected": catering_detected,
        "av_excerpt": av_excerpt,
        "catering_excerpt": catering_excerpt,
    }


def build_dashboard_alert(
    alert_type: str,
    event_name: str,
    detail: str,
    reservation_id: str | None = None,
) -> dict:
    """Build a dashboard alert dict ready for DB insertion.

    Args:
        alert_type: 'av_update' or 'catering_update'
        event_name: Name of the event
        detail: Description of what the client is requesting
        reservation_id: Optional reservation UUID

    Returns:
        {"reservation_id": str|None, "alert_type": str, "title": str, "detail": str}
    """
    title = f"{alert_type.replace('_', ' ').title()}: {event_name}"
    return {
        "reservation_id": reservation_id,
        "alert_type": alert_type,
        "title": title,
        "detail": detail,
    }
