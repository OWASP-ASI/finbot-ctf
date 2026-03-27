"""Route handlers for the OWASP FinBot CTF platform pages"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from finbot.core.templates import TemplateResponse

finbot_templates = TemplateResponse("finbot/apps/finbot/templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """OWASP FinBot CTF home page"""
    return finbot_templates(request, "home.html")


@router.get("/portals", response_class=HTMLResponse)
async def portals(request: Request):
    """Portals page - access vendor, admin, and CTF portals"""
    return finbot_templates(request, "portals.html")


@router.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request):
    """How it works - user-centric guide to the platform"""
    return finbot_templates(request, "how-it-works.html")


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About OWASP FinBot - project info, team, and contributors"""
    return finbot_templates(request, "about.html")


@router.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    """Public platform stats - aggregate community metrics"""
    from finbot.config import settings as _settings  # pylint: disable=import-outside-toplevel

    if not _settings.CC_PUBLIC_STATS_ENABLED:
        return finbot_templates(request, "stats.html", {
            "coming_soon": True,
            "total_users": 0, "active_week": 0, "active_month": 0,
            "challenges_completed": 0, "badges_earned": 0,
            "vendors_registered": 0, "categories": [],
        })

    from finbot.core.analytics.public_stats import get_public_stats  # pylint: disable=import-outside-toplevel
    from finbot.core.data.database import SessionLocal  # pylint: disable=import-outside-toplevel

    db = SessionLocal()
    try:
        data = get_public_stats(db)
    finally:
        db.close()

    data["coming_soon"] = False
    return finbot_templates(request, "stats.html", data)


@router.get("/api/pulse")
async def pulse():
    """Lightweight JSON endpoint for community pulse callout"""
    from finbot.config import settings as _settings  # pylint: disable=import-outside-toplevel

    if not _settings.CC_PUBLIC_STATS_ENABLED:
        return JSONResponse({"enabled": False})

    from finbot.core.analytics.public_stats import get_public_stats  # pylint: disable=import-outside-toplevel
    from finbot.core.data.database import SessionLocal  # pylint: disable=import-outside-toplevel

    db = SessionLocal()
    try:
        data = get_public_stats(db)
    finally:
        db.close()

    return JSONResponse({
        "enabled": True,
        "challenges_completed": data["challenges_completed"],
        "badges_earned": data["badges_earned"],
        "total_users": data["total_users"],
    })


# Error page test routes (for development/testing)
@router.get("/test/404")
async def test_404():
    """Test 404 error page"""
    raise HTTPException(status_code=404, detail="Test 404 error")


@router.get("/test/403")
async def test_403():
    """Test 403 error page"""
    raise HTTPException(status_code=403, detail="Test 403 error")


@router.get("/test/400")
async def test_400():
    """Test 400 error page"""
    raise HTTPException(status_code=400, detail="Test 400 error")


@router.get("/test/500")
async def test_500():
    """Test 500 error page"""
    raise HTTPException(status_code=500, detail="Test 500 error")


@router.get("/test/503")
async def test_503():
    """Test 503 error page"""
    raise HTTPException(status_code=503, detail="Test 503 error")


@router.get("/api/test/404")
async def api_test_404():
    """Test 404 API error response"""
    raise HTTPException(status_code=404, detail="API endpoint not found")


@router.get("/api/test/500")
async def api_test_500():
    """Test 500 API error response"""
    raise HTTPException(status_code=500, detail="Internal API error")
