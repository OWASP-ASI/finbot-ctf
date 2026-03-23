"""Command Center authentication — two-tier access control"""

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

from finbot.config import settings
from finbot.core.data.database import SessionLocal

from .models import PlatformAdmin

logger = logging.getLogger(__name__)


def get_allowed_emails_from_env() -> set[str]:
    """Parse CC_ALLOWED_EMAILS env var into a set of lowercase emails"""
    raw = settings.CC_ALLOWED_EMAILS
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_cc_authorized(email: str | None) -> bool:
    """Check if an email is authorized to access the Command Center.
    Two-tier: DB is the source of truth, env var is bootstrap-only fallback.
    If DB has an explicit is_active=False record, access is denied even if
    the email is in the env var — this allows runtime revocation.
    """
    if not email:
        return False

    email = email.lower().strip()

    db = SessionLocal()
    try:
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.email == email).first()
        if admin:
            return admin.is_active
    finally:
        db.close()

    return email in get_allowed_emails_from_env()


def seed_admins_from_env() -> int:
    """Seed platform_admins table from CC_ALLOWED_EMAILS on first startup.
    Only seeds if the table is empty.
    """
    env_emails = get_allowed_emails_from_env()
    if not env_emails:
        return 0

    db = SessionLocal()
    try:
        existing_count = db.query(PlatformAdmin).count()
        if existing_count > 0:
            return 0

        seeded = 0
        for email in env_emails:
            admin = PlatformAdmin(email=email, added_by="env:CC_ALLOWED_EMAILS")
            db.add(admin)
            seeded += 1

        db.commit()
        logger.info("Seeded %d platform admins from CC_ALLOWED_EMAILS", seeded)
        return seeded
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def cc_auth_guard(request: Request):
    """Middleware-style check for CC routes. Returns 403 HTML if not authorized."""
    session_context = getattr(request.state, "session_context", None)
    email = session_context.email if session_context else None

    if not email or session_context.is_temporary:
        return _forbidden_response("Sign in required to access the Command Center.")

    if not is_cc_authorized(email):
        return _forbidden_response("You are not authorized to access the Command Center.")

    return None


def _forbidden_response(message: str) -> HTMLResponse:
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>403 - Command Center</title>
<style>body{{background:#0c0c14;color:#94a3b8;font-family:Inter,system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{text-align:center;max-width:400px;padding:2rem}}
h1{{color:#ff3366;font-size:1.5rem;margin-bottom:0.5rem}}
a{{color:#00d4ff;text-decoration:none}}</style></head>
<body><div class="box"><h1>Access Denied</h1><p>{message}</p><p><a href="/portals">Back to Portals</a></p></div></body></html>""",
        status_code=403,
    )
