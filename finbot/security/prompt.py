"""Helpers for prompt and goal change security events."""

from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus
from finbot.security.emitter import emit_security_event
from finbot.security.schemas import SecurityEventCategory

CONTENT_PREVIEW_MAX = 200


async def emit_prompt_goal_change(
    *,
    session_context: SessionContext,
    change_type: str,
    source: str,
    content: str,
    agent_name: str | None = None,
    target_agent: str | None = None,
    enriched_from_prior_context: bool = False,
    workflow_id: str | None = None,
    severity: str | None = None,
) -> None:
    """Emit a standardized prompt_goal_change security event."""
    normalized = (content or "").strip()
    if not normalized:
        return

    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    preview = normalized[:CONTENT_PREVIEW_MAX]
    resolved_severity = severity or (
        "warning" if enriched_from_prior_context else "info"
    )

    payload: dict[str, Any] = {
        "change_type": change_type,
        "source": source,
        "content_length": len(normalized),
        "content_preview": preview,
        "enriched_from_prior_context": enriched_from_prior_context,
    }
    if agent_name:
        payload["agent_name"] = agent_name
    if target_agent:
        payload["target_agent"] = target_agent

    summary_agent = target_agent or agent_name or "unknown"
    await emit_security_event(
        category=SecurityEventCategory.prompt_goal_change,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity=resolved_severity,
        summary=f"Security prompt_goal_change: {change_type} via {source} ({summary_agent})",
    )
