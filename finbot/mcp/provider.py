"""MCPToolProvider -- reusable bridge between agents and MCP servers.

Discovers tools from connected MCP servers, converts their schemas to the
OpenAI function-calling format used by BaseAgent, and creates async callables
that wrap MCP client.call_tool() invocations.
"""

import json
import logging
import time
from typing import Any, Callable

from fastmcp import Client, FastMCP

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import MCPActivityLogRepository
from finbot.core.messaging import event_bus
from finbot.security.tools import emit_tool_output, emit_tool_parameters

logger = logging.getLogger(__name__)

# Separator between server name and tool name in namespaced tool IDs
TOOL_NS_SEP = "__"


def _safe_serialize(value: Any) -> Any:
    """Convert value to JSON-safe representation for event data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    return str(value)


class MCPToolProvider:
    """Discovers and invokes tools from MCP servers.

    Connects to one or more MCP servers (in-memory FastMCP instances or remote URLs),
    discovers their tools via the MCP protocol, and exposes them as OpenAI-compatible
    tool definitions + async callables for the agent loop.

    Tool names are namespaced as '{server_name}__{tool_name}' to avoid collisions.
    """

    def __init__(
        self,
        servers: dict[str, FastMCP | str],
        session_context: SessionContext,
        workflow_id: str | None = None,
        agent_name: str | None = None,
    ):
        self._server_sources = servers
        self._session_context = session_context
        self._workflow_id = workflow_id
        self._agent_name = agent_name or "unknown_agent"
        self._clients: dict[str, Client] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._tool_server_map: dict[str, str] = {}
        self._connected = False

    async def connect(self) -> None:
        """Connect to all configured MCP servers and discover tools."""
        for server_name, source in self._server_sources.items():
            try:
                client = Client(source)
                await client.__aenter__()
                self._clients[server_name] = client

                tools = await client.list_tools()
                for tool in tools:
                    namespaced_name = f"{server_name}{TOOL_NS_SEP}{tool.name}"
                    self._tools[namespaced_name] = {
                        "server_name": server_name,
                        "original_name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    }
                    self._tool_server_map[namespaced_name] = server_name

                logger.info(
                    "MCP server '%s' connected: %d tools discovered",
                    server_name,
                    len(tools),
                )

                self._log_activity(
                    server_name,
                    "request",
                    "tools/list",
                    payload={"discovered_tools": [t.name for t in tools]},
                )

                tool_descriptions = {
                    t.name: t.description or "" for t in tools
                }
                await event_bus.emit_agent_event(
                    agent_name=self._agent_name,
                    event_type="mcp_tools_discovered",
                    event_subtype="mcp",
                    event_data={
                        "mcp_server": server_name,
                        "tool_count": len(tools),
                        "tools": [t.name for t in tools],
                        "tool_descriptions": tool_descriptions,
                    },
                    session_context=self._session_context,
                    workflow_id=self._workflow_id,
                    summary=f"MCP server '{server_name}': {len(tools)} tools discovered",
                )

            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Failed to connect to MCP server '%s'", server_name)

        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        for server_name, client in self._clients.items():
            try:
                await client.__aexit__(None, None, None)
                logger.info("MCP server '%s' disconnected", server_name)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "Error disconnecting from MCP server '%s'", server_name
                )
        self._clients.clear()
        self._tools.clear()
        self._tool_server_map.clear()
        self._connected = False

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return OpenAI function-calling format tool definitions for all discovered MCP tools."""
        definitions = []
        for namespaced_name, tool_info in self._tools.items():
            schema = tool_info["input_schema"]
            properties = schema.get("properties", {})
            required = schema.get("required", [])

            definitions.append(
                {
                    "type": "function",
                    "name": namespaced_name,
                    "description": tool_info["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                }
            )
        return definitions

    def get_callables(self) -> dict[str, Callable[..., Any]]:
        """Return name -> async callable map for all discovered MCP tools.

        Each callable wraps client.call_tool() with activity logging.
        """
        callables: dict[str, Callable[..., Any]] = {}
        for namespaced_name, tool_info in self._tools.items():
            server_name = tool_info["server_name"]
            original_name = tool_info["original_name"]
            callables[namespaced_name] = self._make_tool_callable(
                server_name, original_name, namespaced_name
            )
        return callables

    def _make_tool_callable(
        self, server_name: str, original_name: str, namespaced_name: str
    ) -> Callable[..., Any]:
        """Create an async callable that invokes a tool via MCP client."""

        async def call_mcp_tool(**kwargs: Any) -> Any:
            client = self._clients.get(server_name)
            if not client:
                return {"error": f"MCP server '{server_name}' not connected"}

            tool_description = self._tools.get(namespaced_name, {}).get("description", "")

            start = time.time()
            self._log_activity(
                server_name,
                "request",
                "tools/call",
                tool_name=original_name,
                payload={"arguments": kwargs},
            )

            await event_bus.emit_agent_event(
                agent_name=self._agent_name,
                event_type="mcp_tool_call_start",
                event_subtype="mcp",
                event_data={
                    "mcp_server": server_name,
                    "tool_name": original_name,
                    "namespaced_tool_name": namespaced_name,
                    "tool_description": tool_description,
                    "tool_arguments": _safe_serialize(kwargs),
                },
                session_context=self._session_context,
                workflow_id=self._workflow_id,
                summary=f"MCP tool call: {namespaced_name}",
            )
            await emit_tool_parameters(
                session_context=self._session_context,
                agent_name=self._agent_name,
                tool_name=original_name,
                tool_source="mcp",
                arguments=_safe_serialize(kwargs),
                source="mcp.provider",
                mapped_from_event_type="mcp_tool_call_start",
                workflow_id=self._workflow_id,
                mcp_server=server_name,
                namespaced_tool_name=namespaced_name,
            )

            try:
                result = await client.call_tool(original_name, kwargs)
                duration_ms = (time.time() - start) * 1000

                output = result.data if result.data is not None else str(result.content)

                self._log_activity(
                    server_name,
                    "response",
                    "tools/call",
                    tool_name=original_name,
                    payload={"result": str(output)[:1000]},
                    duration_ms=duration_ms,
                )

                await event_bus.emit_agent_event(
                    agent_name=self._agent_name,
                    event_type="mcp_tool_call_success",
                    event_subtype="mcp",
                    event_data={
                        "mcp_server": server_name,
                        "tool_name": original_name,
                        "namespaced_tool_name": namespaced_name,
                        "tool_description": tool_description,
                        "tool_arguments": _safe_serialize(kwargs),
                        "tool_output": str(output)[:2000],
                        "duration_ms": duration_ms,
                    },
                    session_context=self._session_context,
                    workflow_id=self._workflow_id,
                    summary=f"MCP tool completed: {namespaced_name} ({duration_ms:.0f}ms)",
                )
                await emit_tool_output(
                    session_context=self._session_context,
                    agent_name=self._agent_name,
                    tool_name=original_name,
                    tool_source="mcp",
                    source="mcp.provider",
                    mapped_from_event_type="mcp_tool_call_success",
                    workflow_id=self._workflow_id,
                    output=str(output)[:2000],
                    success=True,
                    duration_ms=duration_ms,
                    mcp_server=server_name,
                    namespaced_tool_name=namespaced_name,
                )

                logger.debug(
                    "MCP tool '%s' completed in %.0fms",
                    namespaced_name,
                    duration_ms,
                )
                return output

            except Exception as e:  # pylint: disable=broad-exception-caught
                duration_ms = (time.time() - start) * 1000
                self._log_activity(
                    server_name,
                    "response",
                    "tools/call",
                    tool_name=original_name,
                    payload={"error": str(e)},
                    duration_ms=duration_ms,
                )

                await event_bus.emit_agent_event(
                    agent_name=self._agent_name,
                    event_type="mcp_tool_call_failure",
                    event_subtype="mcp",
                    event_data={
                        "mcp_server": server_name,
                        "tool_name": original_name,
                        "namespaced_tool_name": namespaced_name,
                        "tool_arguments": _safe_serialize(kwargs),
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "duration_ms": duration_ms,
                    },
                    session_context=self._session_context,
                    workflow_id=self._workflow_id,
                    summary=f"MCP tool failed: {namespaced_name} ({type(e).__name__})",
                )
                await emit_tool_output(
                    session_context=self._session_context,
                    agent_name=self._agent_name,
                    tool_name=original_name,
                    tool_source="mcp",
                    source="mcp.provider",
                    mapped_from_event_type="mcp_tool_call_failure",
                    workflow_id=self._workflow_id,
                    success=False,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    mcp_server=server_name,
                    namespaced_tool_name=namespaced_name,
                )

                logger.exception("MCP tool '%s' failed", namespaced_name)
                return {"error": f"MCP tool call failed: {str(e)}"}

        return call_mcp_tool

    def _log_activity(
        self,
        server_name: str,
        direction: str,
        method: str,
        tool_name: str | None = None,
        payload: dict | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log MCP activity to the database for the admin portal."""
        try:
            with db_session() as db:
                repo = MCPActivityLogRepository(db, self._session_context)
                repo.log_activity(
                    server_type=server_name,
                    direction=direction,
                    method=method,
                    tool_name=tool_name,
                    payload_json=json.dumps(payload) if payload else None,
                    workflow_id=self._workflow_id,
                    duration_ms=duration_ms,
                )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to log MCP activity", exc_info=True)

    @property
    def is_connected(self) -> bool:
        """Return True if the MCPToolProvider is connected to all MCP servers."""
        return self._connected

    @property
    def tool_count(self) -> int:
        """Return the number of tools discovered by the MCPToolProvider."""
        return len(self._tools)
