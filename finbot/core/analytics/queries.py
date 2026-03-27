"""Reusable analytics query functions for both public stats and CC dashboard"""

# pylint: disable=not-callable

import math
from datetime import UTC, datetime, timedelta
from itertools import groupby
from operator import attrgetter

from sqlalchemy import case, distinct, func, or_
from sqlalchemy.orm import Session

from .models import PageView

_HUMAN = or_(PageView.device_type != "bot", PageView.device_type.is_(None))


def _since(days: int | None) -> datetime | None:
    if days:
        return datetime.now(UTC) - timedelta(days=days)
    return None


def _percentile(sorted_values: list[int | float], p: float) -> float:
    """Compute the p-th percentile from a pre-sorted list."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_values[int(k)])
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def get_pageviews_count(db: Session, days: int = 7) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    return (
        db.query(func.count(PageView.id))
        .filter(PageView.timestamp >= since, _HUMAN)
        .scalar() or 0
    )


def get_bot_pageviews_count(db: Session, days: int = 7) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    return (
        db.query(func.count(PageView.id))
        .filter(PageView.timestamp >= since, PageView.device_type == "bot")
        .scalar() or 0
    )


def get_unique_visitors(db: Session, days: int = 7) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    return (
        db.query(func.count(distinct(PageView.session_id)))
        .filter(PageView.timestamp >= since, PageView.session_id.isnot(None), _HUMAN)
        .scalar()
        or 0
    )


def get_top_pages(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(PageView.path, func.count(PageView.id).label("views"))
        .filter(PageView.timestamp >= since, _HUMAN)
        .group_by(PageView.path)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"path": r.path, "views": r.views} for r in rows]


def get_browser_breakdown(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(PageView.browser, func.count(PageView.id).label("count"))
        .filter(PageView.timestamp >= since, PageView.browser.isnot(None))
        .group_by(PageView.browser)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"browser": r.browser, "count": r.count} for r in rows]


def get_device_breakdown(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(PageView.device_type, func.count(PageView.id).label("count"))
        .filter(PageView.timestamp >= since, PageView.device_type.isnot(None))
        .group_by(PageView.device_type)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"device": r.device_type, "count": r.count} for r in rows]


def get_referer_breakdown(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(PageView.referer_domain, func.count(PageView.id).label("count"))
        .filter(
            PageView.timestamp >= since,
            PageView.referer_domain.isnot(None),
            PageView.referer_domain != "",
        )
        .group_by(PageView.referer_domain)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )
    return [{"domain": r.referer_domain, "count": r.count} for r in rows]


def get_daily_pageviews(db: Session, days: int | None = 30) -> list[dict]:
    q = db.query(
        func.date(PageView.timestamp).label("day"),
        func.count(PageView.id).label("views"),
        func.count(distinct(PageView.session_id)).label("visitors"),
    )
    if days:
        q = q.filter(PageView.timestamp >= datetime.now(UTC) - timedelta(days=days))
    rows = (
        q.group_by(func.date(PageView.timestamp))
        .order_by(func.date(PageView.timestamp))
        .all()
    )
    return [
        {"day": str(r.day), "views": r.views, "visitors": r.visitors} for r in rows
    ]


def get_auth_funnel(db: Session, days: int = 7) -> dict:
    """Track portals → magic-link → verify conversion"""
    since = datetime.now(UTC) - timedelta(days=days)

    def count_path(path_prefix: str) -> int:
        return (
            db.query(func.count(PageView.id))
            .filter(PageView.timestamp >= since, PageView.path.like(f"{path_prefix}%"))
            .scalar()
            or 0
        )

    return {
        "portals_visits": count_path("/portals"),
        "magic_link_requests": count_path("/auth/magic-link"),
        "verifications": count_path("/auth/verify"),
    }


def get_session_type_breakdown(db: Session, days: int = 7) -> dict:
    """Return unique session counts split by temp vs perm."""
    since = _since(days)
    q = (
        db.query(
            PageView.session_type,
            func.count(distinct(PageView.session_id)).label("sessions"),
        )
        .filter(PageView.session_id.isnot(None), PageView.session_type.isnot(None))
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = q.group_by(PageView.session_type).all()
    result = {"perm": 0, "temp": 0}
    for r in rows:
        if r.session_type in result:
            result[r.session_type] = r.sessions
    result["total"] = result["perm"] + result["temp"]
    return result


def get_response_time_avg(db: Session, days: int = 7) -> float:
    since = datetime.now(UTC) - timedelta(days=days)
    result = (
        db.query(func.avg(PageView.response_time_ms))
        .filter(PageView.timestamp >= since, PageView.response_time_ms.isnot(None))
        .scalar()
    )
    return round(result or 0, 1)


def get_response_time_percentiles(
    db: Session, days: int = 7, path: str | None = None,
) -> dict:
    """Return {avg, p50, p95, p99} response times in ms."""
    since = _since(days)
    q = (
        db.query(PageView.response_time_ms)
        .filter(PageView.response_time_ms.isnot(None))
        .order_by(PageView.response_time_ms)
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    if path:
        q = q.filter(PageView.path == path)
    values = [r[0] for r in q.all()]
    if not values:
        return {"avg": 0, "p50": 0, "p95": 0, "p99": 0}
    return {
        "avg": round(sum(values) / len(values), 1),
        "p50": round(_percentile(values, 50), 1),
        "p95": round(_percentile(values, 95), 1),
        "p99": round(_percentile(values, 99), 1),
    }


def get_daily_latency(
    db: Session, days: int | None = 30, path: str | None = None,
) -> list[dict]:
    """Return daily [{day, avg_ms, p95_ms}]. Computes percentiles in Python."""
    since = _since(days)
    q = (
        db.query(
            func.date(PageView.timestamp).label("day"),
            PageView.response_time_ms,
        )
        .filter(PageView.response_time_ms.isnot(None))
        .order_by(func.date(PageView.timestamp), PageView.response_time_ms)
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    if path:
        q = q.filter(PageView.path == path)

    results = []
    for day, rows in groupby(q.all(), key=attrgetter("day")):
        vals = sorted(r.response_time_ms for r in rows)
        results.append({
            "day": str(day),
            "avg_ms": round(sum(vals) / len(vals), 1),
            "p95_ms": round(_percentile(vals, 95), 1),
        })
    return results


# ---------------------------------------------------------------------------
# Page-scoped queries for the drill-down view
# ---------------------------------------------------------------------------

def get_page_stats(db: Session, path: str, days: int = 7) -> dict:
    """Aggregate stats for a single path."""
    since = _since(days)
    base = db.query(PageView).filter(PageView.path == path)
    if since:
        base = base.filter(PageView.timestamp >= since)

    views = base.count()
    visitors = (
        base.filter(PageView.session_id.isnot(None))
        .with_entities(func.count(distinct(PageView.session_id)))
        .scalar() or 0
    )
    latency = get_response_time_percentiles(db, days=days, path=path)

    error_count = base.filter(PageView.status_code >= 400).count()
    error_rate = round(error_count / views * 100, 1) if views else 0

    return {
        "views": views,
        "visitors": visitors,
        "error_rate": error_rate,
        **latency,
    }


def get_page_daily(db: Session, path: str, days: int | None = 30) -> list[dict]:
    """Daily views + visitors for one path."""
    since = _since(days)
    q = db.query(
        func.date(PageView.timestamp).label("day"),
        func.count(PageView.id).label("views"),
        func.count(distinct(PageView.session_id)).label("visitors"),
    ).filter(PageView.path == path)
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = (
        q.group_by(func.date(PageView.timestamp))
        .order_by(func.date(PageView.timestamp))
        .all()
    )
    return [{"day": str(r.day), "views": r.views, "visitors": r.visitors} for r in rows]


def get_page_status_breakdown(db: Session, path: str, days: int = 7) -> list[dict]:
    """Status code bucket counts for one path."""
    since = _since(days)
    bucket = case(
        (PageView.status_code < 300, "2xx"),
        (PageView.status_code < 400, "3xx"),
        (PageView.status_code < 500, "4xx"),
        else_="5xx",
    ).label("bucket")
    q = (
        db.query(bucket, func.count(PageView.id).label("count"))
        .filter(PageView.path == path)
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = q.group_by(bucket).order_by(bucket).all()
    return [{"status": r.bucket, "count": r.count} for r in rows]


def get_page_browser_breakdown(
    db: Session, path: str, days: int = 7, limit: int = 10,
) -> list[dict]:
    since = _since(days)
    q = (
        db.query(PageView.browser, func.count(PageView.id).label("count"))
        .filter(PageView.path == path, PageView.browser.isnot(None))
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = q.group_by(PageView.browser).order_by(func.count(PageView.id).desc()).limit(limit).all()
    return [{"browser": r.browser, "count": r.count} for r in rows]


def get_page_device_breakdown(
    db: Session, path: str, days: int = 7, limit: int = 10,
) -> list[dict]:
    since = _since(days)
    q = (
        db.query(PageView.device_type, func.count(PageView.id).label("count"))
        .filter(PageView.path == path, PageView.device_type.isnot(None))
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = q.group_by(PageView.device_type).order_by(func.count(PageView.id).desc()).limit(limit).all()
    return [{"device": r.device_type, "count": r.count} for r in rows]


def get_page_referer_breakdown(
    db: Session, path: str, days: int = 7, limit: int = 10,
) -> list[dict]:
    since = _since(days)
    q = (
        db.query(PageView.referer_domain, func.count(PageView.id).label("count"))
        .filter(
            PageView.path == path,
            PageView.referer_domain.isnot(None),
            PageView.referer_domain != "",
        )
    )
    if since:
        q = q.filter(PageView.timestamp >= since)
    rows = q.group_by(PageView.referer_domain).order_by(func.count(PageView.id).desc()).limit(limit).all()
    return [{"domain": r.referer_domain, "count": r.count} for r in rows]


def get_total_pageviews(db: Session) -> int:
    return db.query(func.count(PageView.id)).filter(_HUMAN).scalar() or 0
