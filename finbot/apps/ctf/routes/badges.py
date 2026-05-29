"""Badge API Routes"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import BadgeRepository, UserBadgeRepository
from finbot.core.utils import to_utc_iso
from finbot.ctf.evaluators import create_evaluator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["badges"])


class BadgeListItem(BaseModel):
    """Badge list item model"""

    id: str
    title: str
    description: str
    category: str
    rarity: str
    points: int
    icon_url: str | None
    earned: bool
    earned_at: str | None
    is_secret: bool


class BadgeDetail(BaseModel):
    """Badge detail model"""

    id: str
    title: str
    description: str
    category: str
    rarity: str
    points: int
    icon_url: str | None
    earned: bool
    earned_at: str | None
    progress: dict | None


@router.get("/badges", response_model=list[BadgeListItem])
def list_badges(
    category: str | None = Query(None),
    earned_only: bool = Query(False),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """List all badges with earned status"""
    badge_repo = BadgeRepository(db)
    badges = badge_repo.list_badges(category=category, include_secret=True)

    # Get user's earned badges
    earned_ids = set()
    earned_map = {}
    if session_context:
        user_badge_repo = UserBadgeRepository(db, session_context)
        earned_badges = user_badge_repo.get_earned_badges()
        earned_ids = {b.badge_id for b in earned_badges}
        earned_map = {b.badge_id: b for b in earned_badges}

    result = []
    for badge in badges:
        earned = badge.id in earned_ids

        # Filter by earned if requested
        if earned_only and not earned:
            continue

        user_badge = earned_map.get(badge.id)

        # Mask secret badge details unless earned
        if badge.is_secret and not earned:
            result.append(
                BadgeListItem(
                    id=badge.id,
                    title="???",
                    description="Hidden achievement waiting to be discovered.",
                    category=badge.category,
                    rarity=badge.rarity,
                    points=badge.points,
                    icon_url=None,
                    earned=False,
                    earned_at=None,
                    is_secret=True,
                )
            )
            continue

        result.append(
            BadgeListItem(
                id=badge.id,
                title=badge.title,
                description=badge.description,
                category=badge.category,
                rarity=badge.rarity,
                points=badge.points,
                icon_url=badge.icon_url,
                earned=earned,
                earned_at=to_utc_iso(user_badge.earned_at) if user_badge else None,
                is_secret=badge.is_secret,
            )
        )

    return result


@router.get("/badges/{badge_id}", response_model=BadgeDetail)
def get_badge(
    badge_id: str,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get badge details with progress"""
    badge_repo = BadgeRepository(db)
    badge = badge_repo.get_badge(badge_id)

    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")

    # Check if earned
    user_badge = None
    earned = False
    if session_context:
        user_badge_repo = UserBadgeRepository(db, session_context)
        user_badge = user_badge_repo.get_user_badge(badge_id)
        earned = user_badge is not None

    # Hide secret badge details unless earned
    if badge.is_secret and not earned:
        raise HTTPException(status_code=404, detail="Badge not found")

    # Get progress if not earned - on demand check
    progress = None
    if not earned and session_context:
        config = json.loads(badge.evaluator_config) if badge.evaluator_config else None
        evaluator = create_evaluator(badge.evaluator_class, badge.id, config)
        if evaluator:
            progress = evaluator.get_progress(
                session_context.namespace, session_context.user_id, db
            )

    return BadgeDetail(
        id=badge.id,
        title=badge.title,
        description=badge.description,
        category=badge.category,
        rarity=badge.rarity,
        points=badge.points,
        icon_url=badge.icon_url,
        earned=earned,
        earned_at=to_utc_iso(user_badge.earned_at) if user_badge else None,
        progress=progress,
    )
