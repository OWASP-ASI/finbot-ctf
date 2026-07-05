"""Security event emitter helper."""

import logging
from datetime import UTC, datetime
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus
from finbot.security.schemas import SecurityEvent, SecurityEventCategory

logger = logging.getLogger(__name__)


async def emit_security_event(
    *,
    category: SecurityEventCategory,
    payload: dict[str, Any],
    session_context: SessionContext,
    workflow_id: str | None = None,
    agent_name: str = "security",
    severity: str = "info",
    summary: str | None = None,
) -> None:
    """Validate and emit a standardized security event."""
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    event = SecurityEvent(
        category=category,
        session_id=session_context.session_id,
        workflow_id=workflow_id or "",
        agent_name=agent_name,
        timestamp=timestamp,
        payload=payload,
        severity=severity,
    )

    event_data = event.model_dump(mode="json")

    try:
        await event_bus.emit_agent_event(
            agent_name=agent_name,
            event_type=category.value,
            event_subtype="security",
            event_data=event_data,
            session_context=session_context,
            workflow_id=workflow_id,
            summary=summary,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to emit security event: category=%s", category.value, exc_info=True
        )