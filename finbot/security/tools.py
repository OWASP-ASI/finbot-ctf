"""Helpers for tool-related security events."""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus
from finbot.security.emitter import emit_security_event
from finbot.security.mappings import MCP_TOOL_NS_SEP, build_native_tool_arguments
from finbot.security.schemas import SecurityEventCategory

logger = logging.getLogger(__name__)

OUTPUT_PREVIEW_MAX = 2000


async def emit_tool_selection(
    *,
    session_context: SessionContext,
    tool_name: str,
    tool_source: str,
    source: str,
    agent_name: str,
    workflow_id: str | None = None,
    iteration: int | None = None,
    call_id: str | None = None,
    valid: bool = True,
    available_tool_count: int | None = None,
    mcp_server: str | None = None,
    severity: str | None = None,
) -> None:
    """Emit a standardized tool_selection security event when the LLM picks a tool."""
    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    resolved_severity = severity or ("warning" if not valid else "info")

    resolved_mcp_server = mcp_server
    if resolved_mcp_server is None and tool_source == "mcp" and MCP_TOOL_NS_SEP in tool_name:
        resolved_mcp_server = tool_name.split(MCP_TOOL_NS_SEP, 1)[0]

    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_source": tool_source,
        "source": source,
        "agent_name": agent_name,
        "valid": valid,
    }
    if iteration is not None:
        payload["iteration"] = iteration
    if call_id is not None:
        payload["call_id"] = call_id
    if available_tool_count is not None:
        payload["available_tool_count"] = available_tool_count
    if resolved_mcp_server is not None:
        payload["mcp_server"] = resolved_mcp_server

    await emit_security_event(
        category=SecurityEventCategory.tool_selection,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity=resolved_severity,
        summary=(
            f"Security tool_selection: {tool_name} ({tool_source}) "
            f"via {source} ({'valid' if valid else 'invalid'})"
        ),
    )


async def emit_tool_parameters(
    *,
    session_context: SessionContext,
    agent_name: str,
    tool_name: str,
    tool_source: str,
    arguments: dict[str, Any],
    source: str,
    mapped_from_event_type: str,
    workflow_id: str | None = None,
    mcp_server: str | None = None,
    namespaced_tool_name: str | None = None,
) -> None:
    """Emit a standardized tool_parameters security event (dual emit alongside operational)."""
    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    resolved_mcp_server = mcp_server
    if (
        resolved_mcp_server is None
        and tool_source == "mcp"
        and namespaced_tool_name
        and MCP_TOOL_NS_SEP in namespaced_tool_name
    ):
        resolved_mcp_server = namespaced_tool_name.split(MCP_TOOL_NS_SEP, 1)[0]

    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_source": tool_source,
        "arguments": arguments,
        "source": source,
        "agent_name": agent_name,
        "mapped_from_event_type": mapped_from_event_type,
    }
    if resolved_mcp_server is not None:
        payload["mcp_server"] = resolved_mcp_server
    if namespaced_tool_name is not None:
        payload["namespaced_tool_name"] = namespaced_tool_name

    await emit_security_event(
        category=SecurityEventCategory.tool_parameters,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity="info",
        summary=f"Security tool_parameters: {tool_name} ({tool_source}) via {source}",
    )


async def emit_tool_output(
    *,
    session_context: SessionContext,
    agent_name: str,
    tool_name: str,
    tool_source: str,
    source: str,
    mapped_from_event_type: str,
    workflow_id: str | None = None,
    output: Any = None,
    success: bool = True,
    duration_ms: float | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    mcp_server: str | None = None,
    namespaced_tool_name: str | None = None,
) -> None:
    """Emit a standardized tool_output security event (dual emit alongside operational)."""
    resolved_workflow_id = event_bus.resolve_workflow_id(workflow_id)
    resolved_mcp_server = mcp_server
    if (
        resolved_mcp_server is None
        and tool_source == "mcp"
        and namespaced_tool_name
        and MCP_TOOL_NS_SEP in namespaced_tool_name
    ):
        resolved_mcp_server = namespaced_tool_name.split(MCP_TOOL_NS_SEP, 1)[0]

    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_source": tool_source,
        "source": source,
        "agent_name": agent_name,
        "success": success,
        "mapped_from_event_type": mapped_from_event_type,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if resolved_mcp_server is not None:
        payload["mcp_server"] = resolved_mcp_server
    if namespaced_tool_name is not None:
        payload["namespaced_tool_name"] = namespaced_tool_name

    if success:
        if output is not None:
            output_str = output if isinstance(output, str) else str(output)
            payload["output"] = output_str[:OUTPUT_PREVIEW_MAX]
    else:
        if error_type:
            payload["error_type"] = error_type
        if error_message:
            payload["error_message"] = error_message

    severity = "info" if success else "warning"
    status = "completed" if success else "failed"
    await emit_security_event(
        category=SecurityEventCategory.tool_output,
        payload=payload,
        session_context=session_context,
        workflow_id=resolved_workflow_id,
        agent_name="security",
        severity=severity,
        summary=f"Security tool_output: {tool_name} ({tool_source}) {status} via {source}",
    )


async def emit_native_tool_parameters(
    *,
    session_context: SessionContext,
    agent_name: str,
    tool_name: str,
    tool_args: list[Any] | None,
    tool_kwargs: dict[str, Any] | None,
    workflow_id: str | None = None,
) -> None:
    """Convenience wrapper for native @agent_tool parameter security events."""
    await emit_tool_parameters(
        session_context=session_context,
        agent_name=agent_name,
        tool_name=tool_name,
        tool_source="native",
        arguments=build_native_tool_arguments(tool_args, tool_kwargs),
        source="agent_tool",
        mapped_from_event_type="tool_call_start",
        workflow_id=workflow_id,
    )


async def emit_native_tool_output(
    *,
    session_context: SessionContext,
    agent_name: str,
    tool_name: str,
    workflow_id: str | None = None,
    output: Any = None,
    success: bool = True,
    duration_ms: float | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """Convenience wrapper for native @agent_tool output security events."""
    mapped_from = "tool_call_success" if success else "tool_call_failure"
    await emit_tool_output(
        session_context=session_context,
        agent_name=agent_name,
        tool_name=tool_name,
        tool_source="native",
        source="agent_tool",
        mapped_from_event_type=mapped_from,
        workflow_id=workflow_id,
        output=output,
        success=success,
        duration_ms=duration_ms,
        error_type=error_type,
        error_message=error_message,
    )
