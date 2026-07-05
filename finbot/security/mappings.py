"""Map operational tool events to standardized security categories.

Operational events (tool_call_*, mcp_tool_call_*) remain the source of truth for
CTF detectors and the activity UI. These helpers normalize their payloads into
the security contract for tool_parameters and tool_output.
"""

from typing import Any

from finbot.security.schemas import SecurityEventCategory

MCP_TOOL_NS_SEP = "__"

# Operational event_type suffixes → security category
TOOL_PARAMETERS_OPERATIONAL_EVENTS = frozenset(
    {"tool_call_start", "mcp_tool_call_start"}
)
TOOL_OUTPUT_OPERATIONAL_EVENTS = frozenset(
    {
        "tool_call_success",
        "tool_call_failure",
        "mcp_tool_call_success",
        "mcp_tool_call_failure",
    }
)

OPERATIONAL_TO_SECURITY_CATEGORY: dict[str, SecurityEventCategory] = {
    "tool_call_start": SecurityEventCategory.tool_parameters,
    "mcp_tool_call_start": SecurityEventCategory.tool_parameters,
    "tool_call_success": SecurityEventCategory.tool_output,
    "tool_call_failure": SecurityEventCategory.tool_output,
    "mcp_tool_call_success": SecurityEventCategory.tool_output,
    "mcp_tool_call_failure": SecurityEventCategory.tool_output,
}


def operational_event_action(event_type: str) -> str:
    """Extract the action suffix from a full event_type (e.g. tool_call_start)."""
    if not event_type:
        return ""
    return event_type.rsplit(".", maxsplit=1)[-1]


def security_category_for_operational_event(event_type: str) -> SecurityEventCategory | None:
    """Return the security category for an operational tool event_type, if any."""
    return OPERATIONAL_TO_SECURITY_CATEGORY.get(operational_event_action(event_type))


def build_native_tool_arguments(
    tool_args: list[Any] | None,
    tool_kwargs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge native tool_args + tool_kwargs into a single arguments dict."""
    arguments: dict[str, Any] = dict(tool_kwargs) if tool_kwargs else {}
    if tool_args:
        arguments["_positional_args"] = tool_args
    return arguments


def extract_tool_arguments_from_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize tool arguments from any operational tool event shape."""
    if event.get("tool_arguments") is not None:
        raw = event["tool_arguments"]
        return raw if isinstance(raw, dict) else {}
    if event.get("arguments") is not None:
        raw = event["arguments"]
        return raw if isinstance(raw, dict) else {}
    if event.get("tool_kwargs") is not None or event.get("tool_args") is not None:
        tool_args = event.get("tool_args")
        tool_kwargs = event.get("tool_kwargs")
        return build_native_tool_arguments(
            tool_args if isinstance(tool_args, list) else None,
            tool_kwargs if isinstance(tool_kwargs, dict) else None,
        )
    return {}


def resolve_tool_name_from_event(event: dict[str, Any]) -> str:
    """Prefer namespaced MCP tool name when present."""
    return str(
        event.get("namespaced_tool_name")
        or event.get("tool_name")
        or ""
    )


def infer_tool_source_from_event(event: dict[str, Any]) -> str:
    """Infer tool_source from operational event fields."""
    event_type = operational_event_action(event.get("event_type", ""))
    if event_type.startswith("mcp_tool_call"):
        return "mcp"
    if event.get("event_subtype") == "chat":
        return "chat"
    if event.get("mcp_server") or event.get("namespaced_tool_name"):
        return "mcp"
    return "native"


def normalize_tool_parameters(event: dict[str, Any]) -> dict[str, Any]:
    """Build a standardized tool_parameters payload from an operational event."""
    tool_name = resolve_tool_name_from_event(event)
    tool_source = infer_tool_source_from_event(event)
    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_source": tool_source,
        "arguments": extract_tool_arguments_from_event(event),
        "mapped_from_event_type": operational_event_action(event.get("event_type", "")),
        "agent_name": event.get("agent_name"),
    }
    if event.get("mcp_server"):
        payload["mcp_server"] = event["mcp_server"]
    if event.get("namespaced_tool_name"):
        payload["namespaced_tool_name"] = event["namespaced_tool_name"]
    return payload


def normalize_tool_output(event: dict[str, Any]) -> dict[str, Any]:
    """Build a standardized tool_output payload from an operational event."""
    action = operational_event_action(event.get("event_type", ""))
    tool_name = resolve_tool_name_from_event(event)
    tool_source = infer_tool_source_from_event(event)
    success = "success" in action

    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_source": tool_source,
        "success": success,
        "mapped_from_event_type": action,
        "agent_name": event.get("agent_name"),
    }
    if event.get("duration_ms") is not None:
        payload["duration_ms"] = event["duration_ms"]
    if event.get("mcp_server"):
        payload["mcp_server"] = event["mcp_server"]
    if event.get("namespaced_tool_name"):
        payload["namespaced_tool_name"] = event["namespaced_tool_name"]

    if success:
        if event.get("tool_output") is not None:
            payload["output"] = event["tool_output"]
    else:
        if event.get("error_type"):
            payload["error_type"] = event["error_type"]
        if event.get("error_message"):
            payload["error_message"] = event["error_message"]

    return payload
