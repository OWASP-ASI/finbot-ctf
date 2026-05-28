"""Admin Portal API Routes -- MCP Server Configuration & Activity"""

import importlib
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import (
    ChatMessageRepository,
    MCPActivityLogRepository,
    MCPServerConfigRepository,
    VendorRepository,
)
from finbot.mcp.servers.findrive.server import DEFAULT_CONFIG as FINDRIVE_DEFAULTS
from finbot.mcp.servers.finmail.repositories import EmailRepository
from finbot.mcp.servers.finmail.server import DEFAULT_CONFIG as FINMAIL_DEFAULTS
from finbot.mcp.servers.finstripe.server import DEFAULT_CONFIG as FINSTRIPE_DEFAULTS
from finbot.mcp.servers.systemutils.server import DEFAULT_CONFIG as SYSTEMUTILS_DEFAULTS
from finbot.mcp.servers.taxcalc.server import DEFAULT_CONFIG as TAXCALC_DEFAULTS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["admin-api"])

# Default server definitions for seeding
MCP_SERVER_DEFAULTS = {
    "finstripe": {
        "display_name": "FinStripe",
        "enabled": True,
        "config": {
            **FINSTRIPE_DEFAULTS,
        },
        "description": "Mock Stripe payment processor for fund transfers to vendor accounts.",
    },
    "findrive": {
        "display_name": "FinDrive",
        "enabled": True,
        "config": {
            **FINDRIVE_DEFAULTS,
        },
        "description": "Mock Google Drive for invoice document storage. Files uploaded here can be read by agents during invoice processing -- the indirect prompt injection delivery mechanism.",
    },
    "taxcalc": {
        "display_name": "TaxCalc",
        "enabled": True,
        "config": {
            **TAXCALC_DEFAULTS,
        },
        "description": "Mock tax calculator for tax rate lookups, calculations, and TIN validation.",
    },
    "systemutils": {
        "display_name": "SystemUtils",
        "enabled": True,
        "config": {
            **SYSTEMUTILS_DEFAULTS,
        },
        "description": "System diagnostic and maintenance tools. Sandboxed -- records attempted commands but executes nothing. Enable for CTF RCE challenges.",
    },
    "finmail": {
        "display_name": "FinMail",
        "enabled": True,
        "config": {
            **FINMAIL_DEFAULTS,
        },
        "description": "Internal email system for vendor and admin communications. Agents use this to send and read messages. Tool descriptions can be overridden for CTF email attack scenarios.",
    },
}


class ServerConfigUpdate(BaseModel):
    config: dict


# =============================================================================
# MCP Server Config endpoints
# =============================================================================


@router.get("/mcp/servers")
async def list_mcp_servers(
    session_context: SessionContext = Depends(get_session_context),
):
    """List all MCP server configs for this namespace, seeding defaults if needed."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)

        configs = repo.list_all()
        existing = {c.server_type: c for c in configs}

        for server_type, defaults in MCP_SERVER_DEFAULTS.items():
            existing_config = existing.get(server_type)
            if not existing_config:
                repo.upsert(
                    server_type=server_type,
                    display_name=defaults["display_name"],
                    enabled=defaults["enabled"],
                    config_json=json.dumps(defaults["config"]),
                )
            elif not existing_config.get_config() and defaults.get("config"):
                repo.upsert(
                    server_type=server_type,
                    display_name=defaults["display_name"],
                    enabled=defaults["enabled"],
                    config_json=json.dumps(defaults["config"]),
                )

        configs = repo.list_all()

        servers = []
        for config in configs:
            server_data = config.to_dict()
            defaults = MCP_SERVER_DEFAULTS.get(config.server_type, {})
            server_data["description"] = defaults.get("description", "")
            servers.append(server_data)

        return {"servers": servers}


@router.get("/mcp/servers/{server_type}")
async def get_mcp_server(
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get config for a specific MCP server."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)

        config = repo.get_by_type(server_type)
        if not config:
            if server_type in MCP_SERVER_DEFAULTS:
                defaults = MCP_SERVER_DEFAULTS[server_type]
                config = repo.upsert(
                    server_type=server_type,
                    display_name=defaults["display_name"],
                    enabled=defaults["enabled"],
                    config_json=json.dumps(defaults["config"]),
                )
            else:
                raise HTTPException(status_code=404, detail="MCP server not found")

        server_data = config.to_dict()
        defaults = MCP_SERVER_DEFAULTS.get(server_type, {})
        server_data["description"] = defaults.get("description", "")

        default_tools = await _get_default_tool_definitions(server_type)
        server_data["default_tools"] = default_tools

        return {"server": server_data}


@router.put("/mcp/servers/{server_type}")
async def update_mcp_server_config(
    server_type: str,
    update: ServerConfigUpdate,
    session_context: SessionContext = Depends(get_session_context),
):
    """Update server-specific settings (payment limits, mock balance, etc.)."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)

        config = repo.update_config(server_type, json.dumps(update.config))
        if not config:
            raise HTTPException(status_code=404, detail="MCP server not found")

        return {"success": True, "server": config.to_dict()}


    # Tool definition overrides have moved to Dark Lab (/darklab/supply-chain)


@router.put("/mcp/servers/{server_type}/toggle")
async def toggle_mcp_server(
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
):
    """Enable/disable an MCP server."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)

        config = repo.toggle_enabled(server_type)
        if not config:
            raise HTTPException(status_code=404, detail="MCP server not found")

        return {"success": True, "server": config.to_dict()}


# =============================================================================
# Admin Messages endpoints
# =============================================================================


@router.get("/messages")
async def get_messages(
    message_type: str | None = None,
    is_read: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get messages for the admin inbox (namespace-scoped)."""
    with db_session() as db:
        repo = EmailRepository(db, session_context)

        messages = repo.list_admin_emails(
            message_type=message_type,
            is_read=is_read,
            limit=limit,
            offset=offset,
        )
        stats = repo.get_admin_email_stats()

        return {
            "messages": [m.to_dict() for m in messages],
            "stats": stats,
        }


@router.get("/messages/stats")
async def get_message_stats(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get admin message stats (unread count, type breakdown)."""
    with db_session() as db:
        repo = EmailRepository(db, session_context)
        return repo.get_admin_email_stats()


@router.get("/messages/contacts")
async def get_message_contacts(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get addressable contacts for email compose autocomplete."""
    from finbot.mcp.servers.finmail.routing import get_admin_address  # pylint: disable=import-outside-toplevel

    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendors = vendor_repo.list_vendors() or []

        contacts = [
            {"email": get_admin_address(session_context.namespace), "name": "Admin", "type": "admin"},
        ]
        for v in vendors:
            contacts.append({"email": v.email, "name": v.company_name, "type": "vendor"})

        return {"contacts": contacts}


@router.get("/messages/{message_id}")
async def get_message(
    message_id: int,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get a specific admin message."""
    with db_session() as db:
        repo = EmailRepository(db, session_context)

        msg = repo.get_email(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        return {"message": msg.to_dict()}


@router.post("/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    session_context: SessionContext = Depends(get_session_context),
):
    """Mark an admin message as read."""
    with db_session() as db:
        repo = EmailRepository(db, session_context)

        msg = repo.get_email(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        msg = repo.mark_as_read(message_id)
        return {"success": True, "message": msg.to_dict()}


@router.post("/messages/read-all")
async def mark_all_messages_read(
    session_context: SessionContext = Depends(get_session_context),
):
    """Mark all admin messages as read."""
    with db_session() as db:
        repo = EmailRepository(db, session_context)

        count = repo.mark_all_admin_as_read()
        return {"success": True, "messages_updated": count}


class ComposeEmailRequest(BaseModel):
    """Compose and send an email"""
    to: list[str]
    subject: str
    body: str
    message_type: str = "general"
    cc: list[str] | None = None
    bcc: list[str] | None = None


@router.post("/messages/send")
async def send_message(
    req: ComposeEmailRequest,
    session_context: SessionContext = Depends(get_session_context),
):
    """Compose and send an email from the admin portal."""
    from finbot.mcp.servers.finmail.routing import get_admin_address, route_and_deliver  # pylint: disable=import-outside-toplevel

    sender_name = session_context.email or "Admin"
    from_addr = get_admin_address(session_context.namespace)

    with db_session() as db:
        repo = EmailRepository(db, session_context)

        result = route_and_deliver(
            db=db,
            repo=repo,
            namespace=session_context.namespace,
            to=req.to,
            subject=req.subject,
            body=req.body,
            message_type=req.message_type,
            sender_name=sender_name,
            sender_type="admin",
            from_address=from_addr,
            cc=req.cc,
            bcc=req.bcc,
        )

        external = [d for d in result.get("deliveries", []) if d["type"] == "external"]
        if external:
            from finbot.core.messaging import event_bus  # pylint: disable=import-outside-toplevel

            await event_bus.emit_business_event(
                event_type="email.external_delivery",
                event_subtype="ctf",
                event_data={
                    "subject": req.subject,
                    "external_addresses": [d["email"] for d in external],
                    "delivery_count": len(external),
                    "source": "admin_portal",
                },
                session_context=session_context,
                summary=f"Email sent to external address: {external[0]['email']}",
            )

        return result


# =============================================================================
# FinDrive endpoints (admin-scoped)
# =============================================================================


@router.get("/findrive")
async def list_admin_files(
    folder: str | None = None,
    file_type: str | None = None,
    limit: int = 100,
    session_context: SessionContext = Depends(get_session_context),
):
    """List admin-scoped files from FinDrive (vendor_id=NULL)."""
    from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository  # pylint: disable=import-outside-toplevel

    with db_session() as db:
        repo = FinDriveFileRepository(db, session_context)
        files = repo.list_files(folder_path=folder, limit=limit)
        admin_files = [f for f in files if f.vendor_id is None]
        if file_type:
            admin_files = [f for f in admin_files if f.file_type == file_type]
        return {
            "files": [f.to_dict() for f in admin_files],
            "total_count": len(admin_files),
        }


@router.get("/findrive/{file_id}")
async def get_admin_file(
    file_id: int,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get a specific admin file's content from FinDrive."""
    from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository  # pylint: disable=import-outside-toplevel

    with db_session() as db:
        repo = FinDriveFileRepository(db, session_context)
        f = repo.get_file(file_id)
        if not f:
            raise HTTPException(status_code=404, detail="File not found")
        return {"file": f.to_dict_with_content()}


# =============================================================================
# MCP Activity Log endpoints
# =============================================================================


@router.get("/mcp/activity")
async def list_mcp_activity(
    server_type: str | None = None,
    workflow_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session_context: SessionContext = Depends(get_session_context),
):
    """List MCP activity log entries."""
    with db_session() as db:
        repo = MCPActivityLogRepository(db, session_context)

        entries = repo.list_activity(
            server_type=server_type,
            workflow_id=workflow_id,
            limit=limit,
            offset=offset,
        )
        total = repo.get_activity_count(server_type=server_type)

        return {
            "entries": [e.to_dict() for e in entries],
            "total_count": total,
        }


# =============================================================================
# Helpers
# =============================================================================


def _make_dummy_session_context():
    """Create a minimal SessionContext for server introspection."""
    from datetime import UTC, datetime

    from finbot.core.auth.session import SessionContext as SC

    return SC(
        session_id="",
        user_id="",
        namespace="__introspect__",
        is_temporary=True,
        csrf_token="",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


_SERVER_INTROSPECTORS = {
    "finstripe": "finbot.mcp.servers.finstripe.server.create_finstripe_server",
    "taxcalc": "finbot.mcp.servers.taxcalc.server.create_taxcalc_server",
    "systemutils": "finbot.mcp.servers.systemutils.server.create_systemutils_server",
    "findrive": "finbot.mcp.servers.findrive.server.create_findrive_server",
    "finmail": "finbot.mcp.servers.finmail.server.create_finmail_server",
}


async def _get_default_tool_definitions(server_type: str) -> list[dict]:
    """Get the default tool definitions for a server type by introspecting the FastMCP server."""
    factory_path = _SERVER_INTROSPECTORS.get(server_type)
    if not factory_path:
        return []

    try:
        module_path, func_name = factory_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        factory_fn = getattr(module, func_name)

        dummy_ctx = _make_dummy_session_context()
        server = factory_fn(dummy_ctx)
        server_tools = await server.list_tools()

        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.parameters if hasattr(tool, "parameters") else {},
            }
            for tool in server_tools
        ]
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to introspect %s tools", server_type, exc_info=True)
    return []


# =============================================================================
# Finance Co-Pilot endpoints
# =============================================================================


class ChatRequest(BaseModel):
    """Chat message request"""
    message: str


@router.post("/copilot/chat")
async def copilot_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    session_context: SessionContext = Depends(get_session_context),
):
    """Stream a chat response from the Finance Co-Pilot."""
    from finbot.agents.chat import CoPilotAssistant  # pylint: disable=import-outside-toplevel

    copilot = CoPilotAssistant(
        session_context=session_context,
        background_tasks=background_tasks,
    )

    return StreamingResponse(
        copilot.stream_response(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/copilot/history")
async def get_copilot_history(
    limit: int = 100,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get chat history for the Finance Co-Pilot."""
    with db_session() as db:
        repo = ChatMessageRepository(db, session_context)
        messages = repo.get_history(limit=limit)
        return {"messages": [m.to_dict() for m in messages]}


@router.delete("/copilot/history")
async def clear_copilot_history(
    session_context: SessionContext = Depends(get_session_context),
):
    """Clear Finance Co-Pilot chat history."""
    with db_session() as db:
        repo = ChatMessageRepository(db, session_context)
        count = repo.clear_history()
        return {"success": True, "messages_deleted": count}
