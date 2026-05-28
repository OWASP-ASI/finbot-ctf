"""Dark Lab API Routes -- Supply Chain attacks and Hacker Toolkit data."""

import importlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session, get_db
from finbot.core.data.repositories import CTFEventRepository, MCPServerConfigRepository
from finbot.core.utils import to_utc_iso
from finbot.mcp.servers.finmail.repositories import EmailRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["darklab-api"])


# =============================================================================
# Supply Chain -- MCP Server tool poisoning
# =============================================================================

_MCP_SERVER_DEFAULTS_IMPORT = "finbot.apps.admin.routes.api"


def _get_mcp_defaults() -> dict:
    """Import MCP_SERVER_DEFAULTS from admin to avoid duplication."""
    mod = importlib.import_module(_MCP_SERVER_DEFAULTS_IMPORT)
    return mod.MCP_SERVER_DEFAULTS


class ToolOverridesUpdate(BaseModel):
    tool_overrides: dict


@router.get("/supply-chain/servers")
async def list_servers_with_tools(
    session_context: SessionContext = Depends(get_session_context),
):
    """List all MCP servers with their tool definitions and overrides."""
    defaults = _get_mcp_defaults()

    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)
        configs = repo.list_all()
        existing = {c.server_type: c for c in configs}

        for server_type, defs in defaults.items():
            if server_type not in existing:
                repo.upsert(
                    server_type=server_type,
                    display_name=defs["display_name"],
                    enabled=defs["enabled"],
                    config_json=json.dumps(defs["config"]),
                )

        configs = repo.list_all()

        servers = []
        for config in configs:
            server_data = config.to_dict()
            defs = defaults.get(config.server_type, {})
            server_data["description"] = defs.get("description", "")
            default_tools = await _get_default_tool_definitions(config.server_type)
            server_data["default_tools"] = default_tools
            servers.append(server_data)

        return {"servers": servers}


@router.get("/supply-chain/servers/{server_type}")
async def get_server_tools(
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
):
    """Get tool definitions and overrides for a specific MCP server."""
    defaults = _get_mcp_defaults()

    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)
        config = repo.get_by_type(server_type)

        if not config:
            if server_type in defaults:
                defs = defaults[server_type]
                config = repo.upsert(
                    server_type=server_type,
                    display_name=defs["display_name"],
                    enabled=defs["enabled"],
                    config_json=json.dumps(defs["config"]),
                )
            else:
                raise HTTPException(status_code=404, detail="MCP server not found")

        server_data = config.to_dict()
        defs = defaults.get(server_type, {})
        server_data["description"] = defs.get("description", "")
        server_data["default_tools"] = await _get_default_tool_definitions(server_type)

        return {"server": server_data}


@router.put("/supply-chain/servers/{server_type}/tools")
async def update_tool_overrides(
    server_type: str,
    update: ToolOverridesUpdate,
    session_context: SessionContext = Depends(get_session_context),
):
    """Update tool definition overrides (supply chain attack surface)."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)
        config = repo.update_tool_overrides(server_type, json.dumps(update.tool_overrides))
        if not config:
            raise HTTPException(status_code=404, detail="MCP server not found")

        logger.info(
            "Tool overrides updated for '%s' in namespace '%s': %d tools modified",
            server_type,
            session_context.namespace,
            len(update.tool_overrides),
        )
        return {"success": True, "server": config.to_dict()}


@router.post("/supply-chain/servers/{server_type}/reset-tools")
async def reset_tool_overrides(
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
):
    """Reset tool overrides to defaults."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)
        config = repo.reset_tool_overrides(server_type)
        if not config:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {"success": True, "server": config.to_dict()}


@router.get("/supply-chain/stats")
async def supply_chain_stats(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get aggregate supply chain stats (poisoned tool count across all servers)."""
    with db_session() as db:
        repo = MCPServerConfigRepository(db, session_context)
        configs = repo.list_all()
        total_overrides = 0
        for config in configs:
            overrides = config.get_tool_overrides()
            total_overrides += len(overrides)
        return {"poisoned_tools": total_overrides, "servers_with_overrides": sum(1 for c in configs if c.get_tool_overrides())}


# =============================================================================
# Hacker Toolkit -- Dead Drop (intercepted emails)
# =============================================================================


class DeadDropMessage(BaseModel):
    id: int
    subject: str
    body: str
    message_type: str
    sender_name: str
    sender_type: str
    from_address: str | None
    to_addresses: list[str] | None
    cc_addresses: list[str] | None
    bcc_addresses: list[str] | None
    is_read: bool
    created_at: str


class DeadDropListResponse(BaseModel):
    messages: list[DeadDropMessage]
    total: int
    has_more: bool


class DeadDropStatsResponse(BaseModel):
    total: int
    unread: int


def _email_to_dead_drop(email) -> DeadDropMessage:
    """Convert an Email model to a DeadDropMessage."""
    def parse_addrs(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    return DeadDropMessage(
        id=email.id,
        subject=email.subject,
        body=email.body,
        message_type=email.message_type,
        sender_name=email.sender_name,
        sender_type=email.sender_type,
        from_address=email.from_address,
        to_addresses=parse_addrs(email.to_addresses),
        cc_addresses=parse_addrs(email.cc_addresses),
        bcc_addresses=parse_addrs(email.bcc_addresses),
        is_read=email.is_read,
        created_at=email.created_at.isoformat().replace("+00:00", "Z"),
    )


@router.get("/toolkit/dead-drop", response_model=DeadDropListResponse)
def list_dead_drop(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """List intercepted emails sent to external/unresolvable addresses."""
    repo = EmailRepository(db, session_context)
    stats = repo.get_external_email_stats()
    emails = repo.list_external_emails(limit=limit + 1, offset=offset)

    has_more = len(emails) > limit
    emails = emails[:limit]

    return DeadDropListResponse(
        messages=[_email_to_dead_drop(e) for e in emails],
        total=stats["total"],
        has_more=has_more,
    )


@router.get("/toolkit/dead-drop/stats", response_model=DeadDropStatsResponse)
def dead_drop_stats(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get dead drop message counts."""
    repo = EmailRepository(db, session_context)
    stats = repo.get_external_email_stats()
    return DeadDropStatsResponse(**stats)


@router.get("/toolkit/dead-drop/{message_id}")
def read_dead_drop_message(
    message_id: int,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Read a specific intercepted email."""
    repo = EmailRepository(db, session_context)
    email = repo.get_email(message_id)

    if not email or email.inbox_type != "external":
        return {"error": "Message not found"}

    if not email.is_read:
        repo.mark_as_read(message_id)

    return {"message": _email_to_dead_drop(email)}


# =============================================================================
# Hacker Toolkit -- Exfil Data (captured network requests)
# =============================================================================


class ExfilCapture(BaseModel):
    id: int
    url: str
    method: str
    headers: str
    body: str
    agent_name: str | None
    workflow_id: str | None
    timestamp: str


class ExfilListResponse(BaseModel):
    captures: list[ExfilCapture]
    total: int
    has_more: bool


class ExfilStatsResponse(BaseModel):
    total: int


def _event_to_exfil(event) -> ExfilCapture | None:
    """Extract network_request tool arguments from a CTFEvent."""
    details = {}
    if event.details:
        try:
            details = json.loads(event.details)
        except (ValueError, TypeError):
            pass

    args = details.get("tool_arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            args = {}

    return ExfilCapture(
        id=event.id,
        url=args.get("url", ""),
        method=args.get("method", "GET"),
        headers=args.get("headers", ""),
        body=args.get("body", ""),
        agent_name=event.agent_name,
        workflow_id=event.workflow_id,
        timestamp=to_utc_iso(event.timestamp),
    )


@router.get("/toolkit/exfil-data", response_model=ExfilListResponse)
def list_exfil_data(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """List captured network requests (exfil tool calls)."""
    repo = CTFEventRepository(db, session_context)
    total = repo.count_exfil_events()
    events = repo.get_exfil_events(limit=limit + 1, offset=offset)

    has_more = len(events) > limit
    events = events[:limit]

    return ExfilListResponse(
        captures=[c for e in events if (c := _event_to_exfil(e))],
        total=total,
        has_more=has_more,
    )


@router.get("/toolkit/exfil-data/stats", response_model=ExfilStatsResponse)
def exfil_data_stats(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get exfil capture count."""
    repo = CTFEventRepository(db, session_context)
    return ExfilStatsResponse(total=repo.count_exfil_events())


@router.get("/toolkit/exfil-data/{event_id}")
def read_exfil_capture(
    event_id: int,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Read a specific exfil capture."""
    from finbot.core.data.models import CTFEvent  # pylint: disable=import-outside-toplevel

    event = (
        db.query(CTFEvent)
        .filter(
            CTFEvent.id == event_id,
            CTFEvent.namespace == session_context.namespace,
            CTFEvent.user_id == session_context.user_id,
            CTFEvent.tool_name.in_(CTFEventRepository.EXFIL_TOOL_NAMES),
        )
        .first()
    )
    if not event:
        return {"error": "Capture not found"}

    return {"capture": _event_to_exfil(event)}


# =============================================================================
# Helpers -- Server introspection (shared with admin)
# =============================================================================

_SERVER_INTROSPECTORS = {
    "finstripe": "finbot.mcp.servers.finstripe.server.create_finstripe_server",
    "taxcalc": "finbot.mcp.servers.taxcalc.server.create_taxcalc_server",
    "systemutils": "finbot.mcp.servers.systemutils.server.create_systemutils_server",
    "findrive": "finbot.mcp.servers.findrive.server.create_findrive_server",
    "finmail": "finbot.mcp.servers.finmail.server.create_finmail_server",
}


def _make_dummy_session_context():
    from datetime import UTC, datetime  # pylint: disable=import-outside-toplevel

    return SessionContext(
        session_id="",
        user_id="",
        namespace="__introspect__",
        is_temporary=True,
        csrf_token="",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


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
