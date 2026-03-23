"""CC Access management — manage platform admin allowlist"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from finbot.core.data.database import SessionLocal
from finbot.core.templates import TemplateResponse

from ..models import PlatformAdmin

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/access")


@router.get("/", response_class=HTMLResponse)
async def access_list(request: Request):
    """View and manage CC access list"""
    db = SessionLocal()
    try:
        admins = (
            db.query(PlatformAdmin)
            .order_by(PlatformAdmin.added_at.desc())
            .all()
        )
        admin_list = [
            {
                "id": a.id,
                "email": a.email,
                "added_by": a.added_by or "—",
                "added_at": a.added_at.strftime("%Y-%m-%d %H:%M") if a.added_at else "—",
                "is_active": a.is_active,
            }
            for a in admins
        ]
    finally:
        db.close()

    return template_response(request, "pages/access.html", {"admins": admin_list})


@router.post("/add")
async def add_admin(request: Request, email: str = Form(...)):
    """Add a new platform admin"""
    session_ctx = getattr(request.state, "session_context", None)
    added_by = session_ctx.email if session_ctx else "unknown"

    email = email.lower().strip()
    if not email:
        return RedirectResponse(url="/cc/access", status_code=303)

    db = SessionLocal()
    try:
        existing = db.query(PlatformAdmin).filter(PlatformAdmin.email == email).first()
        if existing:
            existing.is_active = True
            existing.added_by = added_by
        else:
            db.add(PlatformAdmin(email=email, added_by=added_by))
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/cc/access", status_code=303)


@router.post("/toggle/{admin_id}")
async def toggle_admin(admin_id: int):
    """Activate/deactivate a platform admin"""
    db = SessionLocal()
    try:
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.id == admin_id).first()
        if admin:
            admin.is_active = not admin.is_active
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/cc/access", status_code=303)
