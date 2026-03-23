"""Command Center desktop/landing page"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import distinct, func

from finbot.config import settings
from finbot.core.data.database import SessionLocal
from finbot.core.data.models import UserBadge, UserChallengeProgress, Vendor
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter()


def _get_pulse_stats() -> dict:
    """Fetch platform pulse stats for the CC desktop"""
    # pylint: disable=not-callable
    db = SessionLocal()
    try:
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        total_users = db.query(func.count(distinct(Vendor.namespace))).scalar() or 0

        challenges_today = (
            db.query(func.count(UserChallengeProgress.id))
            .filter(
                UserChallengeProgress.status == "completed",
                UserChallengeProgress.completed_at >= today_start,
            )
            .scalar()
            or 0
        )

        badges_total = db.query(func.count(UserBadge.id)).scalar() or 0

        vendors_total = db.query(func.count(Vendor.id)).scalar() or 0

        return {
            "total_users": total_users,
            "challenges_today": challenges_today,
            "badges_total": badges_total,
            "vendors_total": vendors_total,
        }
    finally:
        db.close()


@router.get("/", response_class=HTMLResponse)
async def desktop(request: Request):
    """CC desktop — OS-style launcher with pulse, health, and app grid"""
    pulse = _get_pulse_stats()
    apps = []

    apps.append({"name": "Access", "description": "Manage CC maintainer allowlist", "url": "/cc/access", "icon": "users", "enabled": True})

    if settings.CC_ANALYTICS_ENABLED:
        apps.append({"name": "Analytics", "description": "Traffic, funnels, CTF metrics", "url": "/cc/analytics", "icon": "chart", "enabled": True})

    apps.append({"name": "Audit", "description": "Platform event audit trail", "url": "/cc/audit", "icon": "log", "enabled": True})

    apps.append({"name": "Badges", "description": "Browse and manage CTF badges", "url": "/cc/badges", "icon": "badge", "enabled": True})

    if settings.CC_CERTIFICATES_ENABLED:
        apps.append({"name": "Certificates", "description": "Generate workshop certs", "url": "/cc/certificates", "icon": "certificate", "enabled": True})

    apps.append({"name": "Challenges", "description": "Browse and manage CTF challenges", "url": "/cc/challenges", "icon": "puzzle", "enabled": True})

    apps.append({"name": "Health", "description": "Service status and latency", "url": "/cc/health", "icon": "health", "enabled": True, "new_tab": True})

    apps.append({"name": "Users", "description": "User management and session admin", "url": "/cc/users", "icon": "user-mgmt", "enabled": True})

    return template_response(
        request,
        "pages/desktop.html",
        {
            "apps": apps,
            "pulse": pulse,
        },
    )
