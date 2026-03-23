"""Command Center — FastAPI sub-application"""

from fastapi import FastAPI, Request
from fastapi.responses import Response

from finbot.config import settings
from finbot.core.error_handlers import register_error_handlers

from .auth import cc_auth_guard
from .routes.access import router as access_router
from .routes.audit import router as audit_router
from .routes.badges import router as badges_router
from .routes.challenges import router as challenges_router
from .routes.dashboard import router as dashboard_router
from .routes.health import router as health_router
from .routes.users import router as users_router

app = FastAPI(
    title="OWASP FinBot Command Center",
    description="Platform management for FinBot CTF maintainers",
    version="0.1.0",
    debug=settings.DEBUG,
)

register_error_handlers(app)


@app.middleware("http")
async def enforce_cc_auth(request: Request, call_next) -> Response:
    """Gate all CC routes behind maintainer auth"""
    forbidden = await cc_auth_guard(request)
    if forbidden:
        return forbidden
    return await call_next(request)


app.include_router(dashboard_router)
app.include_router(access_router)
app.include_router(health_router)
app.include_router(challenges_router)
app.include_router(badges_router)
app.include_router(users_router)
app.include_router(audit_router)

if settings.CC_ANALYTICS_ENABLED:
    from .routes.analytics import router as analytics_router  # pylint: disable=ungrouped-imports

    app.include_router(analytics_router)
