"""CC Analytics dashboard routes"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from finbot.core.analytics.probe_queries import (
    get_bot_traffic_overview,
    get_bot_ua_breakdown,
    get_daily_bot_traffic,
    get_daily_probes,
    get_probe_categories,
    get_probe_overview,
    get_top_bot_crawled_pages,
    get_top_probed_paths,
    get_top_sources,
)
from finbot.core.analytics.ctf_queries import (
    get_badges_by_rarity,
    get_challenges_by_category,
    get_challenges_by_difficulty,
    get_ctf_overview,
    get_ctf_session_breakdown,
    get_daily_completions,
    get_daily_events,
    get_events_count,
    get_recent_badges,
    get_top_agents,
    get_top_badges_earned,
    get_top_challenges,
    get_top_event_types,
    get_top_players,
    get_top_tools,
    get_unsolved_challenges,
    get_profile_adoption,
    get_share_link_stats,
)
from finbot.core.analytics.queries import (
    get_api_calls_count,
    get_api_latency_percentiles,
    get_auth_funnel,
    get_bot_pageviews_count,
    get_browser_breakdown,
    get_daily_latency,
    get_daily_pageviews,
    get_device_breakdown,
    get_page_browser_breakdown,
    get_page_daily,
    get_page_device_breakdown,
    get_page_referer_breakdown,
    get_page_stats,
    get_page_status_breakdown,
    get_pageviews_count,
    get_referer_breakdown,
    get_response_time_percentiles,
    get_session_type_breakdown,
    get_top_api_endpoints,
    get_top_pages,
    get_total_pageviews,
    get_unique_visitors,
)
from finbot.core.data.database import SessionLocal
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/analytics")

ALLOWED_DAILY_RANGES = {0, 7, 14, 30}


def _sanitize_days(days: int) -> int:
    return days if days in ALLOWED_DAILY_RANGES else 30


@router.get("/", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """Analytics overview dashboard"""
    db = SessionLocal()
    try:
        latency = get_response_time_percentiles(db, days=7)
        data = {
            "pageviews_7d": get_pageviews_count(db, days=7),
            "pageviews_30d": get_pageviews_count(db, days=30),
            "visitors_7d": get_unique_visitors(db, days=7),
            "visitors_30d": get_unique_visitors(db, days=30),
            "bot_views_7d": get_bot_pageviews_count(db, days=7),
            "bot_views_30d": get_bot_pageviews_count(db, days=30),
            "total_pageviews": get_total_pageviews(db),
            "top_pages": get_top_pages(db, days=7, limit=10),
            "browsers": get_browser_breakdown(db, days=7),
            "devices": get_device_breakdown(db, days=7),
            "referers": get_referer_breakdown(db, days=7, limit=8),
            "daily": get_daily_pageviews(db, days=30),
            "daily_latency": get_daily_latency(db, days=30),
            "funnel": get_auth_funnel(db, days=7),
            "latency": latency,
            "sessions": get_session_type_breakdown(db, days=7),
            "api_calls_7d": get_api_calls_count(db, days=7),
            "api_calls_30d": get_api_calls_count(db, days=30),
            "api_latency": get_api_latency_percentiles(db, days=7),
            "top_api_endpoints": get_top_api_endpoints(db, days=7, limit=10),
        }
    finally:
        db.close()

    return template_response(request, "pages/analytics.html", data)


@router.get("/pages", response_class=HTMLResponse)
async def page_drilldown(request: Request, path: str = Query(...)):
    """Per-page drill-down analytics"""
    db = SessionLocal()
    try:
        data = {
            "path": path,
            "stats": get_page_stats(db, path, days=7),
            "daily": get_page_daily(db, path, days=30),
            "daily_latency": get_daily_latency(db, days=30, path=path),
            "status_codes": get_page_status_breakdown(db, path, days=7),
            "browsers": get_page_browser_breakdown(db, path, days=7),
            "devices": get_page_device_breakdown(db, path, days=7),
            "referers": get_page_referer_breakdown(db, path, days=7),
        }
    finally:
        db.close()

    return template_response(request, "pages/analytics_page.html", data)


@router.get("/api/daily")
async def daily_traffic_api(days: int = Query(default=30)):
    """JSON endpoint for daily traffic, used by the time-range picker."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_pageviews(db, days=days or None)
    finally:
        db.close()


@router.get("/api/daily-latency")
async def daily_latency_api(days: int = Query(default=30)):
    """JSON endpoint for daily latency, used by the time-range picker."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_latency(db, days=days or None)
    finally:
        db.close()


@router.get("/ctf", response_class=HTMLResponse)
async def ctf_analytics(request: Request):
    """CTF analytics dashboard tab"""
    db = SessionLocal()
    try:
        data = {
            "overview": get_ctf_overview(db),
            "events_7d": get_events_count(db, days=7),
            "by_difficulty": get_challenges_by_difficulty(db),
            "by_category": get_challenges_by_category(db),
            "top_challenges": get_top_challenges(db, limit=10),
            "unsolved": get_unsolved_challenges(db),
            "top_players": get_top_players(db, limit=10),
            "badges_by_rarity": get_badges_by_rarity(db),
            "top_badges": get_top_badges_earned(db, limit=10),
            "recent_badges": get_recent_badges(db, limit=10),
            "daily_completions": get_daily_completions(db, days=30),
            "daily_events": get_daily_events(db, days=30),
            "top_event_types": get_top_event_types(db, days=7, limit=10),
            "top_agents": get_top_agents(db, days=7, limit=8),
            "top_tools": get_top_tools(db, days=7, limit=8),
            "ctf_sessions": get_ctf_session_breakdown(db),
            "profile_adoption": get_profile_adoption(db),
            "share_stats": get_share_link_stats(db, days=7),
        }
    finally:
        db.close()

    return template_response(request, "pages/analytics_ctf.html", data)


@router.get("/api/daily-events")
async def daily_events_api(days: int = Query(default=30)):
    """JSON endpoint for daily event volume."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_events(db, days=days or None)
    finally:
        db.close()


@router.get("/api/daily-completions")
async def daily_completions_api(days: int = Query(default=30)):
    """JSON endpoint for daily challenge completions."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_completions(db, days=days or None)
    finally:
        db.close()


@router.get("/threat-intel", response_class=HTMLResponse)
async def threat_intel(request: Request):
    """Threat Intel — probe/scan traffic analysis"""
    db = SessionLocal()
    try:
        overview = get_probe_overview(db, days=7)
        data = {
            "overview": overview,
            "daily_probes": get_daily_probes(db, days=30),
            "top_paths": get_top_probed_paths(db, days=7, limit=15),
            "top_sources": get_top_sources(db, days=7, limit=10),
            "categories": get_probe_categories(db, days=7),
            "bot_overview": get_bot_traffic_overview(db, days=7),
            "bot_top_pages": get_top_bot_crawled_pages(db, days=7, limit=10),
            "bot_agents": get_bot_ua_breakdown(db, days=7, limit=10),
            "daily_bot": get_daily_bot_traffic(db, days=30),
        }
    finally:
        db.close()

    return template_response(request, "pages/analytics_threat_intel.html", data)


@router.get("/api/daily-probes")
async def daily_probes_api(days: int = Query(default=30)):
    """JSON endpoint for daily probe volume."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_probes(db, days=days or None)
    finally:
        db.close()


@router.get("/api/daily-bot-traffic")
async def daily_bot_traffic_api(days: int = Query(default=30)):
    """JSON endpoint for daily bot crawl volume on valid routes."""
    days = _sanitize_days(days)
    db = SessionLocal()
    try:
        return get_daily_bot_traffic(db, days=days or None)
    finally:
        db.close()
