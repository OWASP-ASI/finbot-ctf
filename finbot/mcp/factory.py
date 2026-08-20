"""MCP Server Factory -- creates ephemeral, namespace-scoped MCP server instances.

Each agent run gets a fresh server instance configured for the user's namespace.
The factory reads MCPServerConfig from the DB, applies tool overrides, and
returns a ready-to-use FastMCP server.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import MCPServerConfigRepository

logger = logging.getLogger(__name__)

# Registry of server creation functions
_SERVER_FACTORIES: dict[str, Any] = {
    "finstripe": "finbot.mcp.servers.finstripe.server.create_finstripe_server",
    "taxcalc": "finbot.mcp.servers.taxcalc.server.create_taxcalc_server",
    "systemutils": "finbot.mcp.servers.systemutils.server.create_systemutils_server",
    "findrive": "finbot.mcp.servers.findrive.server.create_findrive_server",
    "finmail": "finbot.mcp.servers.finmail.server.create_finmail_server",
}


def _import_factory(dotted_path: str) -> Any:
    """Lazily import a server factory function by dotted path."""
    module_path, func_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, func_name)


async def _apply_tool_overrides(server: FastMCP, overrides: dict) -> None:
    """Apply user-supplied tool overrides to a FastMCP server.

    Modifies tool descriptions and/or parameter schemas (the text and
    schema the LLM sees) via the provider's get_tool() API. This is the
    primary CTF attack surface for tool poisoning -- both description
    poisoning and parameter-schema poisoning.

    Accepts "parameters" or "inputSchema" as the override key for the
    schema (both are used in the wild -- "inputSchema" is the MCP
    wire-protocol field name, "parameters" is fastmcp's internal Tool
    attribute name that actually needs to be set for the override to take
    effect; setting an "inputSchema" attribute directly on a Tool object
    does nothing, since that name isn't a declared field there).
    """
    if not overrides:
        return

    provider = server.providers[0] if server.providers else None
    if not provider:
        return

    for tool_name, override in overrides.items():
        if not isinstance(override, dict):
            # Malformed top-level structure (e.g. a tool's override is a
            # bare string, not an object). The API-level validator rejects
            # this at write time, but nothing guarantees every row in the
            # DB went through that path (a future direct write, a seed
            # script, a migration). override.get(...) below would raise
            # AttributeError on a non-dict, uncaught -- crashing server
            # creation entirely, not just tool listing. Skip it instead.
            logger.warning(
                "Ignoring malformed override for '%s': expected an object, got %r",
                tool_name,
                type(override).__name__,
            )
            continue

        new_description = override.get("description")
        if new_description is not None and not isinstance(new_description, str):
            # Same failure shape as the parameters case below: succeeds
            # silently on plain attribute assignment, then fails later in
            # to_mcp_tool() when this server's tools are next listed.
            logger.warning(
                "Ignoring non-string description override for '%s': %r",
                tool_name,
                type(new_description).__name__,
            )
            new_description = None

        # Presence-check, not truthiness: a deliberate "parameters": {}
        # override (stripping every param off a tool) is falsy and must
        # not be silently dropped the same way the original bug dropped
        # parameters entirely.
        if "parameters" in override:
            new_parameters = override["parameters"]
        elif "inputSchema" in override:
            new_parameters = override["inputSchema"]
        else:
            new_parameters = None

        if new_parameters is not None and not isinstance(new_parameters, dict):
            # A non-dict schema doesn't fail here (pydantic doesn't
            # validate on plain attribute assignment) -- it fails later,
            # in unrelated code that lists this server's tools, breaking
            # tool discovery entirely until the override is reset. Reject
            # it at the one place that actually writes to the live tool.
            logger.warning(
                "Ignoring non-dict parameters override for '%s': %r",
                tool_name,
                type(new_parameters).__name__,
            )
            new_parameters = None

        if not new_description and new_parameters is None:
            continue

        try:
            tool = await provider.get_tool(tool_name)
            if not tool:
                continue
            if new_description:
                tool.description = new_description
            if new_parameters is not None:
                tool.parameters = new_parameters
            logger.debug(
                "Applied tool override for '%s': description=%s parameters=%s",
                tool_name,
                bool(new_description),
                new_parameters is not None,
            )
        except Exception:
            logger.debug("Tool '%s' not found for override", tool_name)


async def create_mcp_server(
    server_type: str,
    session_context: SessionContext,
) -> FastMCP | None:
    """Create a namespace-scoped MCP server instance.

    1. Loads MCPServerConfig from DB for (server_type, namespace)
    2. Creates the FastMCP server with merged config
    3. Applies tool_overrides_json to modify tool definitions
    4. Returns ready-to-use server, or None if server type is unknown/disabled
    """
    factory_path = _SERVER_FACTORIES.get(server_type)
    if not factory_path:
        logger.warning("Unknown MCP server type: %s", server_type)
        return None

    with db_session() as db:
        config_repo = MCPServerConfigRepository(db, session_context)
        db_config = config_repo.get_by_type(server_type)

        server_config: dict[str, Any] = {}
        tool_overrides: dict = {}

        if db_config:
            if not db_config.enabled:
                logger.info(
                    "MCP server '%s' is disabled for namespace '%s'",
                    server_type,
                    session_context.namespace,
                )
                return None

            server_config = db_config.get_config()
            tool_overrides = db_config.get_tool_overrides()

    factory_fn = _import_factory(factory_path)
    server = factory_fn(
        session_context=session_context,
        server_config=server_config,
    )

    if tool_overrides:
        await _apply_tool_overrides(server, tool_overrides)
        logger.info(
            "Applied %d tool overrides for '%s' in namespace '%s'",
            len(tool_overrides),
            server_type,
            session_context.namespace,
        )

    return server
