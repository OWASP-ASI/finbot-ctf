"""Vendor Portal Web Routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import VendorRepository
from finbot.core.templates import TemplateResponse

# Setup templates
template_response = TemplateResponse("finbot/apps/vendor/templates")

# Create web router
router = APIRouter(tags=["vendor-web"])


@router.get("/", response_class=HTMLResponse, name="vendor_home")
async def vendor_home(
    _: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor portal home - redirect to onboarding or dashboard
    - If the user's namespace has 0 records of vendors, redirect to onboarding
    - If the user's namespace has 1 or more records of vendors, redirect to dashboard
    """
    db = next(get_db())
    vendor_count = VendorRepository(db, session_context).get_vendor_count()
    if vendor_count == 0:
        return RedirectResponse(url="/vendor/onboarding", status_code=302)
    else:
        return RedirectResponse(url="/vendor/dashboard", status_code=302)


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def onboarding(
    request: Request, _: SessionContext = Depends(get_session_context)
):
    """Vendor onboarding page"""
    return template_response(request, "onboarding.html")


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor dashboard"""
    return template_response(
        request, "dashboard.html", {"session_context": session_context}
    )
