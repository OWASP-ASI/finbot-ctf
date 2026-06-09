"""WebSocket Event Types"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from finbot.core.utils import to_utc_iso


class WSEventType(str, Enum):
    """WebSocket event types"""

    # Connection events
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    ERROR = "error"

    # CTF events
    ACTIVITY = "activity"
    CHALLENGE_COMPLETED = "challenge_completed"
    BADGE_EARNED = "badge_earned"
    CHALLENGE_PROGRESS = "challenge_progress"

    # System events
    PING = "ping"
    PONG = "pong"


@dataclass
class WSEvent:
    """WebSocket event structure"""

    type: WSEventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: to_utc_iso(datetime.now(UTC)))

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(
            {
                "type": self.type.value if isinstance(self.type, WSEventType) else self.type,
                "data": self.data,
                "timestamp": self.timestamp,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "WSEvent":
        """Deserialize from JSON"""
        parsed = json.loads(data)
        return cls(
            type=WSEventType(parsed["type"]),
            data=parsed.get("data", {}),
            timestamp=parsed.get("timestamp", to_utc_iso(datetime.now(UTC))),
        )


def create_activity_event(event_data: dict, category: str | None = None) -> WSEvent:
    """Create activity stream event"""
    return WSEvent(
        type=WSEventType.ACTIVITY,
        data={
            "event_type": event_data.get("event_type"),
            "category": category or event_data.get("event_category"),
            "summary": event_data.get("summary"),
            "severity": event_data.get("severity", "info"),
            "workflow_id": event_data.get("workflow_id"),
            "agent_name": event_data.get("agent_name"),
        },
    )


def create_challenge_completed_event(
    challenge_id: str,
    challenge_title: str,
    points: int,
    effective_points: int | None = None,
    points_modifier: float | None = None,
    modifier_details: list[dict] | None = None,
) -> WSEvent:
    """Create challenge completed event"""
    data: dict = {
        "challenge_id": challenge_id,
        "challenge_title": challenge_title,
        "points": points,
    }
    if effective_points is not None:
        data["effective_points"] = effective_points
    if points_modifier is not None and points_modifier < 1.0:
        data["points_modifier"] = points_modifier
    if modifier_details:
        data["modifier_details"] = modifier_details
    return WSEvent(type=WSEventType.CHALLENGE_COMPLETED, data=data)


def create_badge_earned_event(badge_id: str, badge_title: str, rarity: str) -> WSEvent:
    """Create badge earned event"""
    return WSEvent(
        type=WSEventType.BADGE_EARNED,
        data={
            "badge_id": badge_id,
            "badge_title": badge_title,
            "rarity": rarity,
        },
    )
