"""Dark Lab Portal Web Routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/darklab/templates")

router = APIRouter(tags=["darklab-web"])


@router.get("/", response_class=HTMLResponse, name="darklab_home")
async def darklab_home(
    _: Request, session_context: SessionContext = Depends(get_session_context)
):
    return RedirectResponse(url="/darklab/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse, name="darklab_dashboard")
async def darklab_dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/dashboard.html",
        {"request": request},
    )


@router.get("/supply-chain", response_class=HTMLResponse, name="darklab_supply_chain")
async def darklab_supply_chain(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/supply-chain.html",
        {"request": request},
    )


@router.get("/toolkit", response_class=HTMLResponse, name="darklab_toolkit")
async def darklab_toolkit(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    return template_response(
        request,
        "pages/toolkit.html",
        {"request": request},
    )
