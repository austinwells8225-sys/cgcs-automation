from __future__ import annotations

ROOM_CONFIGS: dict[str, dict] = {
    "large_conference": {
        "display_name": "Large Conference Room",
        "max_capacity": 60,
        "equipment": ["projector", "screen", "whiteboard", "microphone", "speakers", "video_conferencing", "wifi"],
        "setups": {"theater": 60, "classroom": 30, "boardroom": 24, "u_shape": 20, "banquet": 40},
    },
    "small_conference": {
        "display_name": "Small Conference Room",
        "max_capacity": 15,
        "equipment": ["projector", "screen", "whiteboard", "video_conferencing", "wifi"],
        "setups": {"boardroom": 15, "u_shape": 10},
    },
    "event_hall": {
        "display_name": "Event Hall",
        "max_capacity": 200,
        "equipment": ["projector", "screen", "microphone", "speakers", "stage", "wifi", "catering_kitchen"],
        "setups": {"theater": 200, "banquet": 120, "reception": 150, "classroom": 80},
    },
    "classroom": {
        "display_name": "Classroom",
        "max_capacity": 40,
        "equipment": ["projector", "screen", "whiteboard", "wifi"],
        "setups": {"classroom": 40, "theater": 40, "u_shape": 20},
    },
    "multipurpose": {
        "display_name": "Multipurpose Room",
        "max_capacity": 80,
        "equipment": ["projector", "screen", "whiteboard", "microphone", "speakers", "wifi"],
        "setups": {"theater": 80, "classroom": 40, "banquet": 50, "reception": 70},
    },
}


def find_suitable_room(attendees: int, requested_room: str | None = None) -> str | None:
    """Find a suitable room for the given attendee count."""
    if requested_room and requested_room in ROOM_CONFIGS:
        if ROOM_CONFIGS[requested_room]["max_capacity"] >= (attendees or 0):
            return requested_room

    # Find smallest room that fits
    for room_key, config in sorted(ROOM_CONFIGS.items(), key=lambda x: x[1]["max_capacity"]):
        if config["max_capacity"] >= (attendees or 0):
            return room_key

    return None
