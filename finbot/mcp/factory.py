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
    """Apply user-supplied tool description overrides to a FastMCP server.

    Modifies tool descriptions (the text the LLM sees) via the provider's
    get_tool() API. This is the primary CTF attack surface for tool poisoning.
    """
    if not overrides:
        return

    provider = server.providers[0] if server.providers else None
    if not provider:
        return

    for tool_name, override in overrides.items():
        new_description = override.get("description")
        if new_description:
            try:
                tool = await provider.get_tool(tool_name)
                if tool:
                    tool.description = new_description
                    logger.debug("Applied tool override for '%s': description updated", tool_name)
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
