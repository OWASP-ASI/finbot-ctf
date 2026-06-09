"""User Stats API Routes"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    UserBadgeRepository,
    UserChallengeProgressRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["stats"])


class CategoryProgress(BaseModel):
    """Category progress model"""

    category: str
    total: int
    completed: int
    percentage: int


class UserStats(BaseModel):
    """User stats model"""

    total_points: int
    challenges_completed: int
    challenges_total: int
    badges_earned: int
    badges_total: int
    hints_used: int
    hints_cost: int
    category_progress: list[CategoryProgress]


@router.get("/stats", response_model=UserStats)
def get_user_stats(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get user's CTF statistics"""
    # Repositories
    challenge_repo = ChallengeRepository(db)
    progress_repo = UserChallengeProgressRepository(db, session_context)
    badge_repo = BadgeRepository(db)
    user_badge_repo = UserBadgeRepository(db, session_context)

    # Get user progress stats
    progress_stats = progress_repo.get_stats()
    completed_progress = progress_repo.get_completed_challenges()
    completed_ids = {p.challenge_id for p in completed_progress}

    # Calculate challenge points (with modifiers applied)
    challenge_points = challenge_repo.get_effective_points(completed_progress)

    # Get badge stats
    earned_badge_ids = list(user_badge_repo.get_earned_badge_ids())
    badge_points = badge_repo.get_total_points(earned_badge_ids)

    # Total points (challenges + badges - hint costs)
    total_points = challenge_points + badge_points - progress_stats["hints_cost"]

    # Get totals
    total_challenges = len(challenge_repo.list_challenges())
    total_badges = badge_repo.count_badges()

    # Category progress
    category_counts = challenge_repo.count_by_category()
    challenges = challenge_repo.list_challenges()

    # Build category progress
    category_progress = []
    for cat, total in category_counts.items():
        # Count completed in this category
        completed_in_cat = sum(1 for c in challenges if c.category == cat and c.id in completed_ids)
        category_progress.append(
            CategoryProgress(
                category=cat,
                total=total,
                completed=completed_in_cat,
                percentage=int((completed_in_cat / total) * 100) if total > 0 else 0,
            )
        )

    return UserStats(
        total_points=total_points,
        challenges_completed=progress_stats["completed_count"],
        challenges_total=total_challenges,
        badges_earned=len(earned_badge_ids),
        badges_total=total_badges,
        hints_used=progress_stats["hints_used"],
        hints_cost=progress_stats["hints_cost"],
        category_progress=category_progress,
    )
