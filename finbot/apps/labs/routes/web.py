"""FinBot Labs — web page routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/labs/templates")

router = APIRouter(tags=["labs-web"])


@router.get("/", response_class=HTMLResponse)
async def labs_home(
    _: Request, session_context: SessionContext = Depends(get_session_context)
):
    return RedirectResponse(url="/labs/guardrails", status_code=302)


@router.get("/guardrails", response_class=HTMLResponse, name="labs_guardrails")
async def labs_guardrails(
    request: Request,
    session_context: SessionContext = Depends(get_session_context),
):
    return template_response(request, "pages/guardrails.html")


@router.get(
    "/guardrails/activity", response_class=HTMLResponse, name="labs_guardrails_activity"
)
async def labs_guardrails_activity(
    request: Request,
    session_context: SessionContext = Depends(get_session_context),
):
    return template_response(request, "pages/activity.html")
