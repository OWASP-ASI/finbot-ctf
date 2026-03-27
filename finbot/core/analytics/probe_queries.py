"""Probe analytics query functions for the CC analytics Probes tab."""

# pylint: disable=not-callable

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from .models import PageView, ProbeLog


def _since(days: int | None) -> datetime | None:
    if days:
        return datetime.now(UTC) - timedelta(days=days)
    return None


def get_probe_overview(db: Session, days: int = 7) -> dict:
    """Top-level probe stats."""
    since = _since(days)
    q = db.query(func.sum(ProbeLog.hits))
    if since:
        q = q.filter(ProbeLog.date >= since.date())
    total_hits = q.scalar() or 0

    q_paths = db.query(func.count(func.distinct(ProbeLog.path)))
    if since:
        q_paths = q_paths.filter(ProbeLog.date >= since.date())
    unique_paths = q_paths.scalar() or 0

    q_sources = db.query(func.count(func.distinct(ProbeLog.source)))
    if since:
        q_sources = q_sources.filter(ProbeLog.date >= since.date())
    unique_sources = q_sources.scalar() or 0

    q_days = db.query(func.count(func.distinct(ProbeLog.date)))
    if since:
        q_days = q_days.filter(ProbeLog.date >= since.date())
    active_days = q_days.scalar() or 0

    avg_daily = round(total_hits / active_days, 1) if active_days else 0

    return {
        "total_hits": total_hits,
        "unique_paths": unique_paths,
        "unique_sources": unique_sources,
        "active_days": active_days,
        "avg_daily": avg_daily,
    }


def get_daily_probes(db: Session, days: int | None = 30) -> list[dict]:
    """Daily probe volume."""
    since = _since(days)
    q = db.query(
        ProbeLog.date,
        func.sum(ProbeLog.hits).label("hits"),
    )
    if since:
        q = q.filter(ProbeLog.date >= since.date())
    rows = q.group_by(ProbeLog.date).order_by(ProbeLog.date).all()
    return [{"day": str(r.date), "hits": int(r.hits)} for r in rows]


def get_top_probed_paths(db: Session, days: int = 7, limit: int = 15) -> list[dict]:
    """Most probed paths."""
    since = _since(days)
    q = db.query(
        ProbeLog.path,
        func.sum(ProbeLog.hits).label("hits"),
    )
    if since:
        q = q.filter(ProbeLog.date >= since.date())
    rows = (
        q.group_by(ProbeLog.path)
        .order_by(func.sum(ProbeLog.hits).desc())
        .limit(limit)
        .all()
    )
    return [{"path": r.path, "hits": int(r.hits)} for r in rows]


def get_top_sources(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    """Top probe sources (scanner identifiers)."""
    since = _since(days)
    q = db.query(
        ProbeLog.source,
        func.sum(ProbeLog.hits).label("hits"),
    )
    if since:
        q = q.filter(ProbeLog.date >= since.date())
    rows = (
        q.group_by(ProbeLog.source)
        .order_by(func.sum(ProbeLog.hits).desc())
        .limit(limit)
        .all()
    )
    return [{"source": r.source or "unknown", "hits": int(r.hits)} for r in rows]


def get_probe_categories(db: Session, days: int = 7) -> list[dict]:
    """Categorize probed paths by what they're looking for."""
    since = _since(days)
    q = db.query(ProbeLog.path, func.sum(ProbeLog.hits).label("hits"))
    if since:
        q = q.filter(ProbeLog.date >= since.date())
    rows = q.group_by(ProbeLog.path).all()

    categories = {
        "CMS / WordPress": 0,
        "Config / Secrets": 0,
        "Admin Panels": 0,
        "Server Info": 0,
        "Code Execution": 0,
        "Database": 0,
        "File Managers": 0,
        "Other": 0,
    }

    for r in rows:
        p = r.path.lower()
        hits = int(r.hits)
        if any(w in p for w in ("wp-", "wordpress", "xmlrpc")):
            categories["CMS / WordPress"] += hits
        elif any(w in p for w in (".env", ".git", "config", ".htaccess", ".htpasswd", ".ini", ".conf", ".yaml", ".yml")):
            categories["Config / Secrets"] += hits
        elif any(w in p for w in ("admin", "phpmyadmin", "manager", "cpanel", "panel")):
            categories["Admin Panels"] += hits
        elif any(w in p for w in ("server-status", "server-info", "actuator", "health", "metrics", "debug", "info")):
            categories["Server Info"] += hits
        elif any(w in p for w in ("shell", "cmd", "console", "cgi", "exec", ".php", ".asp", ".jsp")):
            categories["Code Execution"] += hits
        elif any(w in p for w in ("sql", "dump", "backup", "database", "db")):
            categories["Database"] += hits
        elif any(w in p for w in ("elfinder", "filemanager", "upload", "file")):
            categories["File Managers"] += hits
        else:
            categories["Other"] += hits

    return [
        {"category": k, "hits": v}
        for k, v in sorted(categories.items(), key=lambda x: -x[1])
        if v > 0
    ]


# ---------------------------------------------------------------------------
# Bot crawl traffic on valid app routes (from page_views, not probe_log)
# ---------------------------------------------------------------------------

_BOT = PageView.device_type == "bot"


def get_bot_traffic_overview(db: Session, days: int = 7) -> dict:
    """Summary stats for bot traffic on genuine application routes."""
    since = _since(days)
    base = db.query(PageView).filter(_BOT)
    if since:
        base = base.filter(PageView.timestamp >= since)

    total_hits = base.count()
    unique_pages = (
        base.with_entities(func.count(distinct(PageView.path))).scalar() or 0
    )
    unique_agents = (
        base.with_entities(func.count(distinct(PageView.browser))).scalar() or 0
    )
    return {
        "total_hits": total_hits,
        "unique_pages": unique_pages,
        "unique_agents": unique_agents,
    }


def get_top_bot_crawled_pages(
    db: Session, days: int = 7, limit: int = 10,
) -> list[dict]:
    """App routes most frequently hit by bots."""
    since = _since(days)
    q = (
        db.query(PageView.path, func.count(PageView.id).label("hits"))
        .filter(_BOT)
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = (
        q.group_by(PageView.path)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"path": r.path, "hits": r.hits} for r in rows]


def get_bot_ua_breakdown(
    db: Session, days: int = 7, limit: int = 10,
) -> list[dict]:
    """Which bot types are crawling valid routes."""
    since = _since(days)
    q = (
        db.query(PageView.browser, func.count(PageView.id).label("hits"))
        .filter(_BOT, PageView.browser.isnot(None))
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = (
        q.group_by(PageView.browser)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"agent": r.browser, "hits": r.hits} for r in rows]


def get_daily_bot_traffic(db: Session, days: int | None = 30) -> list[dict]:
    """Daily bot crawl volume on valid routes."""
    since = _since(days)
    q = (
        db.query(
            func.date(PageView.timestamp).label("day"),
            func.count(PageView.id).label("hits"),
        )
        .filter(_BOT)
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = (
        q.group_by(func.date(PageView.timestamp))
        .order_by(func.date(PageView.timestamp))
        .all()
    )
    return [{"day": str(r.day), "hits": r.hits} for r in rows]
