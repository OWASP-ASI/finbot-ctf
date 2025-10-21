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
    """Vendor portal home with vendor context routing"""
    db = next(get_db())
    vendor_repo = VendorRepository(db, session_context)
    vendor_count = vendor_repo.get_vendor_count()

    if vendor_count == 0:
        return RedirectResponse(url="/vendor/onboarding", status_code=302)

    # Check if user needs to select vendor
    if session_context.requires_vendor_selection():
        return RedirectResponse(url="/vendor/select-vendor", status_code=302)

    return RedirectResponse(url="/vendor/dashboard", status_code=302)


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def onboarding(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor onboarding page"""
    return template_response(
        request,
        "onboarding.html",
        {
            "request": request,
            "user_context": {
                "namespace": session_context.namespace,
                "user_id": session_context.user_id,
            },
        },
    )


@router.get("/select-vendor", response_class=HTMLResponse, name="select_vendor")
async def select_vendor(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor selection page"""
    # Check force parameter to bypass redirect
    force = request.query_params.get("force", "").lower() == "true"
    if not force and session_context.has_vendor_context():
        return RedirectResponse(url="/vendor/dashboard", status_code=302)

    return template_response(
        request,
        "pages/select-vendor.html",
        {
            "request": request,
            "available_vendors": session_context.available_vendors,
        },
    )


@router.get("/dashboard", response_class=HTMLResponse, name="vendor_dashboard")
async def vendor_dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor dashboard with current vendor context"""
    # Ensure user has vendor context
    if not session_context.has_vendor_context():
        return RedirectResponse(url="/vendor/select-vendor", status_code=302)

    return template_response(
        request,
        "pages/dashboard.html",
        {
            "request": request,
            "vendor_context": session_context.current_vendor,
            "is_multi_vendor": session_context.is_multi_vendor_user(),
            "available_vendors": session_context.available_vendors,
        },
    )


@router.get("/invoices", response_class=HTMLResponse, name="vendor_invoices")
async def vendor_invoices(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor invoices page"""
    if not session_context.has_vendor_context():
        return RedirectResponse(url="/vendor/select-vendor", status_code=302)

    return template_response(
        request,
        "pages/invoices.html",
        {
            "request": request,
            "vendor_context": session_context.current_vendor,
            "is_multi_vendor": session_context.is_multi_vendor_user(),
        },
    )


@router.get("/payments", response_class=HTMLResponse, name="vendor_payments")
async def vendor_payments(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor payments page"""
    if not session_context.has_vendor_context():
        return RedirectResponse(url="/vendor/select-vendor", status_code=302)

    return template_response(
        request,
        "pages/payments.html",
        {
            "request": request,
            "vendor_context": session_context.current_vendor,
            "is_multi_vendor": session_context.is_multi_vendor_user(),
        },
    )


@router.get("/messages", response_class=HTMLResponse, name="vendor_messages")
async def vendor_messages(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """Vendor messages page"""
    if not session_context.has_vendor_context():
        return RedirectResponse(url="/vendor/select-vendor", status_code=302)

    return template_response(
        request,
        "pages/messages.html",
        {
            "request": request,
            "vendor_context": session_context.current_vendor,
            "is_multi_vendor": session_context.is_multi_vendor_user(),
        },
    )
