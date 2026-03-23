"""Public stats queries — aggregate-only, no PII"""

# pylint: disable=not-callable

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from finbot.core.data.models import (
    Challenge,
    UserBadge,
    UserChallengeProgress,
    Vendor,
)

from .models import PageView


def get_public_stats(db: Session) -> dict:
    """Collect all aggregate stats for the public /stats page"""
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_users = (
        db.query(func.count(distinct(PageView.session_id)))
        .filter(PageView.session_type == "perm")
        .scalar()
        or 0
    )

    active_week = (
        db.query(func.count(distinct(PageView.session_id)))
        .filter(PageView.timestamp >= week_ago, PageView.session_type == "perm")
        .scalar()
        or 0
    )

    active_month = (
        db.query(func.count(distinct(PageView.session_id)))
        .filter(PageView.timestamp >= month_ago, PageView.session_type == "perm")
        .scalar()
        or 0
    )

    challenges_completed = (
        db.query(func.count(UserChallengeProgress.id))
        .filter(UserChallengeProgress.status == "completed")
        .scalar()
        or 0
    )

    badges_earned = db.query(func.count(UserBadge.id)).scalar() or 0

    vendors_registered = db.query(func.count(Vendor.id)).scalar() or 0

    challenge_categories = (
        db.query(
            Challenge.category,
            func.count(UserChallengeProgress.id).label("count"),
        )
        .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
        .filter(UserChallengeProgress.status == "completed")
        .group_by(Challenge.category)
        .order_by(func.count(UserChallengeProgress.id).desc())
        .all()
    )
    categories = [{"name": r.category, "count": r.count} for r in challenge_categories]

    return {
        "total_users": total_users,
        "active_week": active_week,
        "active_month": active_month,
        "challenges_completed": challenges_completed,
        "badges_earned": badges_earned,
        "vendors_registered": vendors_registered,
        "categories": categories,
    }
