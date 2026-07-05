"""Helpers for memory-related security events."""

from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus
from finbot.security.emitter import emit_security_event
from finbot.security.schemas import SecurityEventCategory

MEMORY_KEY_AGENT_NOTES = "agent_notes"
CONTENT_PREVIEW_MAX = 200


async def emit_memory_read(
    *,
    session_context: SessionContext,
    entity_type: str,
    entity_id: int,
    content: str,
    source: str,
    consumer_agent: str | None = None,
    workflow_id: str | None = None,
) -> None:
    """Emit a standardized memory_read security event for agent_notes consumption."""
    normalized = (content or "").strip()
    if not normalized:
        return

    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    preview = normalized[:CONTENT_PREVIEW_MAX]

    payload: dict[str, str | int] = {
        "memory_key": MEMORY_KEY_AGENT_NOTES,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "content_length": len(normalized),
        "content_preview": preview,
        "source": source,
    }
    if consumer_agent:
        payload["consumer_agent"] = consumer_agent

    await emit_security_event(
        category=SecurityEventCategory.memory_read,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity="info",
        summary=(
            f"Security memory_read: {entity_type} {entity_id} via {source}"
            + (f" ({consumer_agent})" if consumer_agent else "")
        ),
    )


async def emit_agent_notes_read(
    *,
    session_context: SessionContext,
    entity_type: str,
    entity_id: int,
    agent_notes: str | None,
    source: str,
    consumer_agent: str | None = None,
    workflow_id: str | None = None,
) -> None:
    """Convenience wrapper for reading agent_notes into agent context."""
    await emit_memory_read(
        session_context=session_context,
        entity_type=entity_type,
        entity_id=entity_id,
        content=agent_notes or "",
        source=source,
        consumer_agent=consumer_agent,
        workflow_id=workflow_id,
    )


async def emit_memory_write(
    *,
    session_context: SessionContext,
    entity_type: str,
    entity_id: int,
    content: str,
    source: str,
    write_mode: str = "append",
    workflow_id: str | None = None,
) -> None:
    """Emit a standardized memory_write security event for agent_notes updates."""
    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    preview = content[:CONTENT_PREVIEW_MAX] if content else ""

    await emit_security_event(
        category=SecurityEventCategory.memory_write,
        payload={
            "memory_key": MEMORY_KEY_AGENT_NOTES,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "write_mode": write_mode,
            "content_length": len(content),
            "content_preview": preview,
            "source": source,
        },
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity="info",
        summary=f"Security memory_write: {entity_type} {entity_id} via {source}",
    )
