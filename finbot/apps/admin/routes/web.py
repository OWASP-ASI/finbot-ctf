"""Admin Portal Web Routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/admin/templates")

router = APIRouter(tags=["admin-web"])


@router.get("/", response_class=HTMLResponse, name="admin_home")
async def admin_home(_: Request, session_context: SessionContext = Depends(get_session_context)):
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
async def admin_dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/dashboard.html",
        {"request": request},
    )


@router.get("/messages", response_class=HTMLResponse, name="admin_messages")
async def admin_messages(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/messages.html",
        {"request": request},
    )


@router.get("/findrive", response_class=HTMLResponse, name="admin_findrive")
async def admin_findrive(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/findrive.html",
        {"request": request},
    )


@router.get("/mcp-servers", response_class=HTMLResponse, name="admin_mcp_servers")
async def admin_mcp_servers(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/mcp-servers.html",
        {"request": request},
    )


@router.get("/mcp-servers/{server_type}", response_class=HTMLResponse, name="admin_mcp_config")
async def admin_mcp_config(
    request: Request,
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
):
    return template_response(
        request,
        "pages/mcp-config.html",
        {"request": request, "server_type": server_type},
    )


@router.get("/mcp-activity", response_class=HTMLResponse, name="admin_mcp_activity")
async def admin_mcp_activity(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/mcp-activity.html",
        {"request": request},
    )
