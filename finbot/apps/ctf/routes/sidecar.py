"""CTF Sidecar Widget API - provides data for the vendor portal CTF widget"""

from datetime import datetime

from fastapi import APIRouter, Depends

from finbot.core.utils import to_utc_iso
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_authenticated_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    CTFEventRepository,
    UserBadgeRepository,
    UserChallengeProgressRepository,
)

router = APIRouter(prefix="/api/v1", tags=["sidecar"])


def _format_utc_timestamp(dt: datetime | None) -> str | None:
    """Format datetime as ISO string with Z suffix for UTC."""
    return to_utc_iso(dt)


@router.get("/sidecar")
async def get_sidecar_data(
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Get CTF data for the sidecar widget"""

    # Repositories
    challenge_repo = ChallengeRepository(db)
    progress_repo = UserChallengeProgressRepository(db, session_context)
    badge_repo = BadgeRepository(db)
    user_badge_repo = UserBadgeRepository(db, session_context)
    event_repo = CTFEventRepository(db, session_context)

    # Get all active challenges
    all_challenges = challenge_repo.list_challenges(active_only=True)
    total_challenges = len(all_challenges)

    # Get user's challenge progress and filter completed ones
    all_progress = progress_repo.get_all_progress()
    completed_progress = [p for p in all_progress if p.status == "completed"]
    completed_count = len(completed_progress)

    # Calculate effective points from completed challenges (with modifiers)
    total_points = challenge_repo.get_effective_points(completed_progress)

    # Get user badges (already ordered by earned_at desc)
    user_badges = user_badge_repo.get_earned_badges()
    badges_data = []
    for ub in user_badges[:6]:  # Limit to 6 most recent
        badge = badge_repo.get_badge(ub.badge_id)
        if badge:
            badges_data.append(
                {
                    "id": badge.id,
                    "title": badge.title,
                    "icon_url": badge.icon_url,
                    "rarity": badge.rarity,
                    "earned_at": _format_utc_timestamp(ub.earned_at),
                }
            )

    # Get recent activity (last 10 events)
    recent_events = event_repo.get_events(limit=10)
    activity_data = []
    for event in recent_events:
        activity_data.append(
            {
                "id": event.id,
                "category": event.event_category,
                "type": event.event_type,
                "summary": event.summary or event.event_type,
                "agent_name": event.agent_name,
                "timestamp": _format_utc_timestamp(event.timestamp),
            }
        )

    # Get in-progress challenges
    in_progress = [p for p in all_progress if p.status == "in_progress"]
    active_challenges = []
    for prog in in_progress[:3]:  # Limit to 3
        challenge = challenge_repo.get_challenge(prog.challenge_id)
        if challenge:
            active_challenges.append(
                {
                    "id": challenge.id,
                    "title": challenge.title,
                    "category": challenge.category,
                    "difficulty": challenge.difficulty,
                    "points": challenge.points,
                    "attempts": prog.attempts,
                }
            )

    # Calculate completion percentage
    completion_pct = (
        round((completed_count / total_challenges) * 100) if total_challenges > 0 else 0
    )

    return {
        "points": total_points,
        "completed": completed_count,
        "total": total_challenges,
        "completion_percentage": completion_pct,
        "badges": badges_data,
        "badges_count": len(user_badges),
        "recent_activity": activity_data,
        "active_challenges": active_challenges,
    }
