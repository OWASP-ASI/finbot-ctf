"""Vendor Portal Web Routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.repositories import VendorRepository

# Setup templates
templates = Jinja2Templates(directory="finbot/apps/vendor/templates")

# Create web router
router = APIRouter(tags=["vendor-web"])


@router.get("/", response_class=HTMLResponse, name="vendor_home")
async def vendor_home(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor portal home - redirect to onboarding or dashboard
    - If the user's namespace has 0 records of vendors, redirect to onboarding
    - If the user's namespace has 1 or more records of vendors, redirect to dashboard
    """
    # vendor_count = await VendorRepository(
    #     request.state.db, request.state.session_context
    # ).get_vendor_count()
    # if vendor_count == 0:
    #     return RedirectResponse(url="/vendor/onboarding", status_code=302)
    # else:
    #     return RedirectResponse(url="/vendor/dashboard", status_code=302)


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def onboarding(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor onboarding page"""
    return templates.TemplateResponse("onboarding.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor dashboard"""
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "session_context": session_context}
    )
