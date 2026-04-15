"""
FinBot Platform Main Application
- Serves all the applications for the FinBot platform.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from finbot.apps.admin.main import app as admin_app
from finbot.apps.darklab.main import app as darklab_app
from finbot.apps.labs import labs_app
from finbot.apps.cc import models as _cc_models  # noqa: F401
from finbot.apps.ctf import ctf_app
from finbot.apps.ctf.rendering import get_renderer
from finbot.apps.finbot.auth import router as auth_router
from finbot.apps.finbot.routes import router as finbot_router
from finbot.apps.vendor.main import app as vendor_app
from finbot.apps.web.routes import router as web_router
from finbot.config import settings
from finbot.core.analytics import models as _analytics_models  # noqa: F401
from finbot.core.auth.csrf import CSRFProtectionMiddleware
from finbot.core.auth.middleware import SessionMiddleware, get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data import (
    models as _models,  # noqa: F401 — register all tables with Base
)
from finbot.core.error_handlers import register_error_handlers
from finbot.core.messaging import event_bus
from finbot.core.websocket import websocket_router

# CTF
from finbot.ctf.processor import start_processor_task

# Logging
from finbot.logging_config import setup_logging
from finbot.mcp.servers.findrive import models as _findrive_models  # noqa: F401
from finbot.mcp.servers.finmail import models as _finmail_models  # noqa: F401
from finbot.mcp.servers.finstripe import models as _finstripe_models  # noqa: F401

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management.

    Only per-worker initialization belongs here. One-time bootstrap tasks
    (migrations, seeding, cleanup, CTF definition loading) run in
    ``scripts/bootstrap.py`` — called by ``run.py`` for local dev and
    by ``docker/entrypoint.sh`` for Docker deployments.
    """

    # 1. Start CTF event processor (Redis consumer groups — multi-worker safe)
    processor_task = None
    try:
        processor_task = start_processor_task()
        print("🚀 CTF event processor started")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ CTF processor start failed: {e}")

    # 2. Pre-warm the Playwright renderer (headless Chromium for OG images)
    renderer = get_renderer()
    try:
        await renderer.start()
        print("🖼️ Playwright renderer ready")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ Playwright renderer start skipped: {e}")

    # 3. Build analytics known-prefix list from registered routes
    if settings.CC_ANALYTICS_ENABLED:
        try:
            from finbot.core.analytics.middleware import build_known_prefixes
            build_known_prefixes(app)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"⚠️ Analytics prefix build skipped: {e}")

    yield  # App is running

    # Shut down Playwright renderer
    try:
        await renderer.shutdown()
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Stop CTF event processor gracefully
    try:
        # pylint: disable=import-outside-toplevel
        from finbot.ctf.processor import get_processor

        processor = get_processor()
        if processor:
            processor.stop()
        if processor_task:
            processor_task.cancel()
            try:
                await processor_task
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Task cancelled
            print("🛑 CTF event processor stopped")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ CTF processor stop failed: {e}")


app = FastAPI(
    title="FinBot Platform",
    description="FinBot Application Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware - last in, first out order
# Analytics runs after session (needs session context), before CSRF
if settings.CC_ANALYTICS_ENABLED:
    from finbot.core.analytics.middleware import AnalyticsMiddleware

    app.add_middleware(AnalyticsMiddleware)

# Execute session first, then CSRF
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(SessionMiddleware)

# Trust X-Forwarded-Proto/For from reverse proxies (Railway, etc.)
# so url_for() generates https:// URLs and client IPs are correct.
from uvicorn.middleware.proxy_headers import (
    ProxyHeadersMiddleware,  # pylint: disable=ungrouped-imports
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Register error handlers
register_error_handlers(app)

# Mount Static Files
app.mount("/static", StaticFiles(directory="finbot/static"), name="static")

# Mount all the applications for the platform
app.mount("/vendor", vendor_app)
app.mount("/admin", admin_app)
app.mount("/darklab", darklab_app)
app.mount("/ctf", ctf_app)
app.mount("/labs", labs_app)

# Command Center — platform management for maintainers
if settings.CC_ENABLED:
    from finbot.apps.cc.main import app as cc_app  # pylint: disable=ungrouped-imports

    app.mount("/cc", cc_app)
app.include_router(websocket_router)
# Auth routes for magic link sign-in
app.include_router(auth_router)
# OWASP FinBot CTF landing pages at root
app.include_router(finbot_router)
# CineFlow demo tenant (hidden, preserved for future IPI scenarios)
app.include_router(web_router, prefix="/demo/cineflow")


# web agreement handler
@app.get("/agreement", response_class=HTMLResponse)
async def agreement(_: Request):
    """FinBot Agreement page"""
    try:
        # (TODO) cache this to reduce disk I/O
        with open("finbot/static/pages/agreement.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=200)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Agreement page not found") from e


# Agreement acceptance audit log
@app.post("/api/log-agreement")
async def log_agreement(
    request: Request,
    session_context: SessionContext = Depends(get_session_context),
):
    """Log user acceptance of the CTF participation agreement for audit purposes."""
    body = await request.json()
    await event_bus.emit_business_event(
        event_type="platform.agreement_accepted",
        event_subtype="lifecycle",
        event_data={
            "user_agent": body.get("userAgent", ""),
            "referrer": body.get("referrer", ""),
        },
        session_context=session_context,
        summary=f"CTF agreement accepted by user {session_context.user_id[:8]}",
    )
    return {"success": True}


@app.get("/healthz")
async def healthz():
    """Lightweight liveness probe for load balancers and container orchestrators."""
    return {"status": "ok"}


# Session health check endpoint
@app.get("/api/session/status")
async def session_status(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get current session status and security information"""
    return {
        "session_id": session_context.session_id[:8] + "...",
        "user_id": session_context.user_id,
        "is_temporary": session_context.is_temporary,
        "namespace": session_context.namespace,
        "security_status": session_context.get_security_status(),
        "csrf_token": session_context.csrf_token,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
