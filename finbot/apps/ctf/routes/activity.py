"""Activity Stream API Routes"""

import json
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.models import Badge, Challenge, UserBadge, UserChallengeProgress
from finbot.core.data.repositories import CTFEventRepository
from finbot.core.utils import to_utc_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["activity"])


class ActivityItem(BaseModel):
    """Activity item model with rich event data"""

    id: int
    event_category: str
    event_type: str
    event_subtype: str | None
    summary: str
    severity: str
    agent_name: str | None
    tool_name: str | None
    llm_model: str | None
    duration_ms: float | None
    workflow_id: str | None
    vendor_id: int | None
    details: dict | None
    timestamp: str


class WorkflowAchievement(BaseModel):
    kind: str  # "challenge" or "badge"
    id: str
    title: str
    status: str
    points: int


class ActivityResponse(BaseModel):
    """Activity response model"""

    items: list[ActivityItem]
    total: int
    page: int
    page_size: int
    has_more: bool
    achievements: dict[str, list[WorkflowAchievement]]


def _build_achievements(
    db: Session, namespace: str, user_id: str
) -> dict[str, list[WorkflowAchievement]]:
    """Build workflow_id -> achievements map from challenge progress and badges."""
    result: dict[str, list[WorkflowAchievement]] = defaultdict(list)

    rows = (
        db.query(UserChallengeProgress, Challenge)
        .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
        .filter(
            UserChallengeProgress.namespace == namespace,
            UserChallengeProgress.user_id == user_id,
        )
        .all()
    )
    for prog, challenge in rows:
        wf_id = prog.completion_workflow_id or prog.last_attempt_workflow_id
        if not wf_id:
            continue
        result[wf_id].append(
            WorkflowAchievement(
                kind="challenge",
                id=prog.challenge_id,
                title=challenge.title,
                status=prog.status,
                points=challenge.points,
            )
        )

    badge_rows = (
        db.query(UserBadge, Badge)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .filter(
            UserBadge.namespace == namespace,
            UserBadge.user_id == user_id,
            UserBadge.earning_workflow_id.isnot(None),
        )
        .all()
    )
    for ub, badge in badge_rows:
        result[ub.earning_workflow_id].append(
            WorkflowAchievement(
                kind="badge",
                id=ub.badge_id,
                title=badge.title,
                status="earned",
                points=badge.points,
            )
        )

    return dict(result)


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    category: str | None = Query(None),
    workflow_id: str | None = Query(None),
    vendor_id: int | None = Query(None),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get paginated activity stream"""
    event_repo = CTFEventRepository(db, session_context)

    total = event_repo.count_events(category=category, workflow_id=workflow_id, vendor_id=vendor_id)

    offset = (page - 1) * page_size
    events = event_repo.get_events(
        limit=page_size + 1,
        offset=offset,
        category=category,
        workflow_id=workflow_id,
        vendor_id=vendor_id,
    )

    has_more = len(events) > page_size
    events = events[:page_size]

    items = []
    for e in events:
        details = None
        if e.details:
            try:
                details = json.loads(e.details)
            except (json.JSONDecodeError, TypeError):
                details = None

        items.append(
            ActivityItem(
                id=e.id,
                event_category=e.event_category,
                event_type=e.event_type,
                event_subtype=e.event_subtype,
                summary=e.summary or f"Event: {e.event_type}",
                severity=e.severity,
                agent_name=e.agent_name,
                tool_name=e.tool_name,
                llm_model=e.llm_model or (details or {}).get("llm_model"),
                duration_ms=round(e.duration_ms) if e.duration_ms is not None else None,
                workflow_id=e.workflow_id,
                vendor_id=e.vendor_id,
                details=details,
                timestamp=to_utc_iso(e.timestamp),
            )
        )

    achievements = _build_achievements(db, session_context.namespace, session_context.user_id)

    return ActivityResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        achievements=achievements,
    )
