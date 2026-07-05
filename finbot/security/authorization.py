"""Helpers for authorization decision security events."""

import asyncio
import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus
from finbot.security.emitter import emit_security_event
from finbot.security.schemas import SecurityEventCategory

logger = logging.getLogger(__name__)


async def emit_authorization_decision(
    *,
    session_context: SessionContext,
    action: str,
    allowed: bool,
    reason: str,
    source: str,
    resource_type: str | None = None,
    resource_id: int | str | None = None,
    requested_vendor_id: int | None = None,
    session_vendor_id: int | None = None,
    portal_type: str | None = None,
    workflow_id: str | None = None,
    severity: str | None = None,
) -> None:
    """Emit a standardized authorization_decision security event."""
    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    resolved_portal = portal_type or session_context.portal_type
    resolved_session_vendor = (
        session_vendor_id
        if session_vendor_id is not None
        else session_context.current_vendor_id
    )
    resolved_severity = severity or ("info" if allowed else "warning")

    payload: dict[str, Any] = {
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "source": source,
    }
    if resource_type is not None:
        payload["resource_type"] = resource_type
    if resource_id is not None:
        payload["resource_id"] = resource_id
    if requested_vendor_id is not None:
        payload["requested_vendor_id"] = requested_vendor_id
    if resolved_session_vendor is not None:
        payload["session_vendor_id"] = resolved_session_vendor
    if resolved_portal is not None:
        payload["portal_type"] = resolved_portal

    await emit_security_event(
        category=SecurityEventCategory.authorization_decision,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity=resolved_severity,
        summary=(
            f"Security authorization_decision: {action} "
            f"{'allowed' if allowed else 'denied'} via {source}"
        ),
    )


def schedule_authorization_decision(**kwargs: Any) -> None:
    """Schedule authorization_decision emission from sync call sites (e.g. MCP tools)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(emit_authorization_decision(**kwargs))
    except RuntimeError:
        try:
            asyncio.run(emit_authorization_decision(**kwargs))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to emit authorization_decision from sync context",
                exc_info=True,
            )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to schedule authorization_decision", exc_info=True)


async def check_vendor_portal_scope(
    *,
    session_context: SessionContext,
    owner_vendor_id: int | None,
    action: str,
    source: str,
    resource_type: str,
    resource_id: int | str | None = None,
    workflow_id: str | None = None,
) -> bool:
    """Evaluate vendor-portal vendor scope and emit authorization_decision."""
    if not session_context.is_vendor_portal():
        await emit_authorization_decision(
            session_context=session_context,
            action=action,
            allowed=True,
            reason="admin_portal_access",
            source=source,
            resource_type=resource_type,
            resource_id=resource_id,
            requested_vendor_id=owner_vendor_id,
            workflow_id=workflow_id,
        )
        return True

    session_vendor_id = session_context.current_vendor_id
    allowed = (
        session_vendor_id is not None and owner_vendor_id == session_vendor_id
    )
    await emit_authorization_decision(
        session_context=session_context,
        action=action,
        allowed=allowed,
        reason="same_vendor" if allowed else "cross_vendor_access_denied",
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        requested_vendor_id=owner_vendor_id,
        session_vendor_id=session_vendor_id,
        workflow_id=workflow_id,
    )
    return allowed


def schedule_vendor_portal_scope_check(
    *,
    session_context: SessionContext,
    owner_vendor_id: int | None,
    action: str,
    source: str,
    resource_type: str,
    resource_id: int | str | None = None,
) -> bool:
    """Sync helper for MCP tools: evaluate scope and return allowed."""
    if not session_context.is_vendor_portal():
        schedule_authorization_decision(
            session_context=session_context,
            action=action,
            allowed=True,
            reason="admin_portal_access",
            source=source,
            resource_type=resource_type,
            resource_id=resource_id,
            requested_vendor_id=owner_vendor_id,
        )
        return True

    session_vendor_id = session_context.current_vendor_id
    allowed = (
        session_vendor_id is not None and owner_vendor_id == session_vendor_id
    )
    schedule_authorization_decision(
        session_context=session_context,
        action=action,
        allowed=allowed,
        reason="same_vendor" if allowed else "cross_vendor_access_denied",
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        requested_vendor_id=owner_vendor_id,
        session_vendor_id=session_vendor_id,
    )
    return allowed
