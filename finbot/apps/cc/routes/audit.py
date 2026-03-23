"""CC Audit — platform event audit trail"""

# pylint: disable=not-callable

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from sqlalchemy import distinct

from finbot.core.data.database import SessionLocal
from finbot.core.data.models import CTFEvent, User
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/audit")

PAGE_SIZE = 50


def _get_filter_options(db) -> dict:
    """Get distinct values for filter dropdowns."""
    categories = [
        r[0] for r in db.query(distinct(CTFEvent.event_category)).order_by(CTFEvent.event_category).all()
        if r[0]
    ]
    severities = [
        r[0] for r in db.query(distinct(CTFEvent.severity)).order_by(CTFEvent.severity).all()
        if r[0]
    ]
    agents = [
        r[0] for r in db.query(distinct(CTFEvent.agent_name))
        .filter(CTFEvent.agent_name.isnot(None))
        .order_by(CTFEvent.agent_name).all()
    ]
    return {"categories": categories, "severities": severities, "agents": agents}


def _query_events(db, *, category=None, severity=None, agent=None, search=None, page=1):
    """Query events with filters and pagination."""
    q = db.query(CTFEvent, User.display_name, User.email).outerjoin(
        User, CTFEvent.user_id == User.user_id
    )

    if category:
        q = q.filter(CTFEvent.event_category == category)
    if severity:
        q = q.filter(CTFEvent.severity == severity)
    if agent:
        q = q.filter(CTFEvent.agent_name == agent)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            (CTFEvent.summary.ilike(pattern))
            | (CTFEvent.event_type.ilike(pattern))
            | (CTFEvent.user_id.ilike(pattern))
        )

    total = q.count()
    offset = (page - 1) * PAGE_SIZE

    rows = (
        q.order_by(CTFEvent.timestamp.desc())
        .offset(offset)
        .limit(PAGE_SIZE)
        .all()
    )

    events = []
    for row in rows:
        e = row.CTFEvent
        details = None
        if e.details:
            try:
                details = json.loads(e.details)
            except (ValueError, TypeError):
                details = e.details

        events.append({
            "id": e.id,
            "timestamp": e.timestamp,
            "event_category": e.event_category,
            "event_type": e.event_type,
            "event_subtype": e.event_subtype,
            "summary": e.summary,
            "details": details,
            "severity": e.severity,
            "user_id": e.user_id,
            "display_name": row.display_name or row.email or (e.user_id[:8] + "..."),
            "agent_name": e.agent_name,
            "tool_name": e.tool_name,
            "llm_model": e.llm_model,
            "duration_ms": e.duration_ms,
            "namespace": e.namespace,
            "vendor_id": e.vendor_id,
            "workflow_id": e.workflow_id,
        })

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return events, total, total_pages


@router.get("/", response_class=HTMLResponse)
async def audit_list(
    request: Request,
    category: str = Query(default=""),
    severity: str = Query(default=""),
    agent: str = Query(default=""),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
):
    """Event audit trail with filters and pagination"""
    db = SessionLocal()
    try:
        filters = _get_filter_options(db)
        events, total, total_pages = _query_events(
            db,
            category=category or None,
            severity=severity or None,
            agent=agent or None,
            search=search or None,
            page=page,
        )

        data = {
            "events": events,
            "filters": filters,
            "active_filters": {
                "category": category,
                "severity": severity,
                "agent": agent,
                "search": search,
            },
            "pagination": {
                "page": page,
                "total_pages": total_pages,
                "total": total,
                "page_size": PAGE_SIZE,
                "has_prev": page > 1,
                "has_next": page < total_pages,
            },
        }
    finally:
        db.close()

    return template_response(request, "pages/audit.html", data)
