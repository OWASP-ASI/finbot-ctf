"""CTF analytics query functions for the CC analytics CTF tab.

Queries against Challenge, UserChallengeProgress, Badge, UserBadge,
CTFEvent, and UserSession tables.
"""

# pylint: disable=not-callable

from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, distinct, func
from sqlalchemy.orm import Session

from finbot.core.analytics.models import PageView
from finbot.core.data.models import (
    Badge,
    Challenge,
    CTFEvent,
    User,
    UserBadge,
    UserChallengeProgress,
    UserProfile,
    UserSession,
)


def _display_name(user_id: str, display_name: str | None, email: str | None) -> str:
    """Show display name, fall back to email, then truncated user_id."""
    if display_name:
        return display_name
    if email:
        return email
    return user_id[:8] + "..."


def _since(days: int | None) -> datetime | None:
    if days:
        return datetime.now(UTC) - timedelta(days=days)
    return None


# ---------------------------------------------------------------------------
# Overview stats
# ---------------------------------------------------------------------------

def get_ctf_overview(db: Session) -> dict:
    """Top-level CTF stats (all-time)."""
    total_challenges = db.query(func.count(Challenge.id)).filter(Challenge.is_active.is_(True)).scalar() or 0

    challenges_cracked = (
        db.query(func.count(distinct(UserChallengeProgress.challenge_id)))
        .filter(UserChallengeProgress.status == "completed")
        .scalar() or 0
    )

    active_players = (
        db.query(func.count(distinct(UserChallengeProgress.user_id)))
        .scalar() or 0
    )
    badges_earned = db.query(func.count(UserBadge.id)).scalar() or 0
    badges_defined = db.query(func.count(Badge.id)).filter(Badge.is_active.is_(True)).scalar() or 0

    avg_solve = (
        db.query(func.avg(UserChallengeProgress.completion_time_seconds))
        .filter(
            UserChallengeProgress.status == "completed",
            UserChallengeProgress.completion_time_seconds.isnot(None),
        )
        .scalar()
    )

    return {
        "total_challenges": total_challenges,
        "challenges_cracked": challenges_cracked,
        "completion_rate": round(challenges_cracked / total_challenges * 100, 1) if total_challenges else 0,
        "active_players": active_players,
        "badges_earned": badges_earned,
        "badges_defined": badges_defined,
        "avg_solve_seconds": int(avg_solve) if avg_solve else 0,
    }


def get_events_count(db: Session, days: int = 7) -> int:
    since = _since(days)
    q = db.query(func.count(CTFEvent.id))
    if since:
        q = q.filter(CTFEvent.timestamp >= since)
    return q.scalar() or 0


# ---------------------------------------------------------------------------
# Challenge breakdowns
# ---------------------------------------------------------------------------

def get_challenges_by_difficulty(db: Session) -> list[dict]:
    """Per-difficulty: total challenges, completed count, completion rate."""
    difficulties = (
        db.query(Challenge.difficulty, func.count(Challenge.id).label("total"))
        .filter(Challenge.is_active.is_(True))
        .group_by(Challenge.difficulty)
        .all()
    )
    result = []
    for row in difficulties:
        completed = (
            db.query(func.count(distinct(UserChallengeProgress.user_id)))
            .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
            .filter(
                Challenge.difficulty == row.difficulty,
                UserChallengeProgress.status == "completed",
            )
            .scalar() or 0
        )
        attempts = (
            db.query(func.count(distinct(UserChallengeProgress.user_id)))
            .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
            .filter(Challenge.difficulty == row.difficulty)
            .scalar() or 0
        )
        result.append({
            "difficulty": row.difficulty,
            "total_challenges": row.total,
            "completions": completed,
            "attempts": attempts,
            "rate": round(completed / attempts * 100, 1) if attempts else 0,
        })

    order = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}
    result.sort(key=lambda x: order.get(x["difficulty"], 99))
    return result


def get_challenges_by_category(db: Session) -> list[dict]:
    """Per-category: total challenges, completed count, completion rate."""
    categories = (
        db.query(Challenge.category, func.count(Challenge.id).label("total"))
        .filter(Challenge.is_active.is_(True))
        .group_by(Challenge.category)
        .order_by(func.count(Challenge.id).desc())
        .all()
    )
    result = []
    for row in categories:
        completed = (
            db.query(func.count(distinct(UserChallengeProgress.user_id)))
            .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
            .filter(
                Challenge.category == row.category,
                UserChallengeProgress.status == "completed",
            )
            .scalar() or 0
        )
        attempts = (
            db.query(func.count(distinct(UserChallengeProgress.user_id)))
            .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
            .filter(Challenge.category == row.category)
            .scalar() or 0
        )
        result.append({
            "category": row.category,
            "total_challenges": row.total,
            "completions": completed,
            "attempts": attempts,
            "rate": round(completed / attempts * 100, 1) if attempts else 0,
        })
    return result


def get_top_challenges(db: Session, limit: int = 10) -> list[dict]:
    """Most-solved challenges by completion count."""
    rows = (
        db.query(
            UserChallengeProgress.challenge_id,
            Challenge.title,
            Challenge.difficulty,
            func.count(UserChallengeProgress.id).label("solves"),
        )
        .join(Challenge, UserChallengeProgress.challenge_id == Challenge.id)
        .filter(UserChallengeProgress.status == "completed")
        .group_by(UserChallengeProgress.challenge_id, Challenge.title, Challenge.difficulty)
        .order_by(func.count(UserChallengeProgress.id).desc())
        .limit(limit)
        .all()
    )
    return [{"title": r.title, "difficulty": r.difficulty, "solves": r.solves} for r in rows]


def get_unsolved_challenges(db: Session) -> list[dict]:
    """Active challenges with zero completions."""
    solved_ids = (
        db.query(distinct(UserChallengeProgress.challenge_id))
        .filter(UserChallengeProgress.status == "completed")
        .subquery()
    )
    rows = (
        db.query(Challenge.title, Challenge.difficulty, Challenge.category)
        .filter(
            Challenge.is_active.is_(True),
            Challenge.id.notin_(db.query(solved_ids)),
        )
        .order_by(Challenge.order_index)
        .all()
    )
    return [{"title": r.title, "difficulty": r.difficulty, "category": r.category} for r in rows]


def get_top_players(db: Session, limit: int = 10) -> list[dict]:
    """Most active players by completed challenges and total attempts."""
    rows = (
        db.query(
            UserChallengeProgress.user_id,
            User.display_name,
            User.email,
            func.sum(
                func.cast(UserChallengeProgress.status == "completed", Integer)
            ).label("completed"),
            func.count(UserChallengeProgress.id).label("attempted"),
            func.sum(UserChallengeProgress.attempts).label("total_attempts"),
        )
        .outerjoin(User, UserChallengeProgress.user_id == User.user_id)
        .group_by(UserChallengeProgress.user_id, User.display_name, User.email)
        .order_by(
            func.sum(func.cast(UserChallengeProgress.status == "completed", Integer)).desc(),
            func.sum(UserChallengeProgress.attempts).desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "display_name": _display_name(r.user_id, r.display_name, r.email),
            "completed": int(r.completed or 0),
            "attempted": r.attempted,
            "total_attempts": int(r.total_attempts or 0),
        }
        for r in rows
    ]


def get_daily_completions(db: Session, days: int | None = 30) -> list[dict]:
    """Daily challenge completion counts."""
    since = _since(days)
    q = db.query(
        func.date(UserChallengeProgress.completed_at).label("day"),
        func.count(UserChallengeProgress.id).label("completions"),
    ).filter(
        UserChallengeProgress.status == "completed",
        UserChallengeProgress.completed_at.isnot(None),
    )
    if since:
        q = q.filter(UserChallengeProgress.completed_at >= since)
    rows = (
        q.group_by(func.date(UserChallengeProgress.completed_at))
        .order_by(func.date(UserChallengeProgress.completed_at))
        .all()
    )
    return [{"day": str(r.day), "completions": r.completions} for r in rows]


def get_top_badges_earned(db: Session, limit: int = 10) -> list[dict]:
    """Most-earned badges by earn count."""
    rows = (
        db.query(
            UserBadge.badge_id,
            Badge.title,
            Badge.rarity,
            func.count(UserBadge.id).label("earned"),
        )
        .join(Badge, UserBadge.badge_id == Badge.id)
        .group_by(UserBadge.badge_id, Badge.title, Badge.rarity)
        .order_by(func.count(UserBadge.id).desc())
        .limit(limit)
        .all()
    )
    return [{"title": r.title, "rarity": r.rarity, "earned": r.earned} for r in rows]


# ---------------------------------------------------------------------------
# Badge breakdowns
# ---------------------------------------------------------------------------

def get_badges_by_rarity(db: Session) -> list[dict]:
    """Per-rarity: total defined, total earned."""
    rarities = (
        db.query(Badge.rarity, func.count(Badge.id).label("defined"))
        .filter(Badge.is_active.is_(True))
        .group_by(Badge.rarity)
        .all()
    )
    order = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
    result = []
    for row in rarities:
        earned = (
            db.query(func.count(UserBadge.id))
            .join(Badge, UserBadge.badge_id == Badge.id)
            .filter(Badge.rarity == row.rarity)
            .scalar() or 0
        )
        result.append({
            "rarity": row.rarity,
            "defined": row.defined,
            "earned": earned,
        })
    result.sort(key=lambda x: order.get(x["rarity"], 99))
    return result


def get_recent_badges(db: Session, limit: int = 10) -> list[dict]:
    """Most recently earned badges."""
    rows = (
        db.query(UserBadge, Badge.title, Badge.rarity, User.display_name, User.email)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .outerjoin(User, UserBadge.user_id == User.user_id)
        .order_by(UserBadge.earned_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "badge_title": r.title,
            "rarity": r.rarity,
            "display_name": _display_name(r.UserBadge.user_id, r.display_name, r.email),
            "earned_at": r.UserBadge.earned_at.isoformat().replace("+00:00", "Z")
            if r.UserBadge.earned_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Activity (CTFEvent)
# ---------------------------------------------------------------------------

def get_daily_events(db: Session, days: int | None = 30) -> list[dict]:
    """Daily event counts split by category (business vs agent)."""
    since = _since(days)
    q = db.query(
        func.date(CTFEvent.timestamp).label("day"),
        CTFEvent.event_category,
        func.count(CTFEvent.id).label("count"),
    )
    if since:
        q = q.filter(CTFEvent.timestamp >= since)
    rows = (
        q.group_by(func.date(CTFEvent.timestamp), CTFEvent.event_category)
        .order_by(func.date(CTFEvent.timestamp))
        .all()
    )

    days_map: dict[str, dict] = {}
    for r in rows:
        day = str(r.day)
        if day not in days_map:
            days_map[day] = {"day": day, "business": 0, "agent": 0}
        if r.event_category in ("business", "agent"):
            days_map[day][r.event_category] = r.count

    return list(days_map.values())


def get_top_event_types(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = _since(days)
    q = (
        db.query(CTFEvent.event_type, func.count(CTFEvent.id).label("count"))
    )
    if since:
        q = q.filter(CTFEvent.timestamp >= since)
    rows = q.group_by(CTFEvent.event_type).order_by(func.count(CTFEvent.id).desc()).limit(limit).all()
    return [{"event_type": r.event_type, "count": r.count} for r in rows]


def get_top_agents(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = _since(days)
    q = (
        db.query(CTFEvent.agent_name, func.count(CTFEvent.id).label("count"))
        .filter(CTFEvent.agent_name.isnot(None))
    )
    if since:
        q = q.filter(CTFEvent.timestamp >= since)
    rows = q.group_by(CTFEvent.agent_name).order_by(func.count(CTFEvent.id).desc()).limit(limit).all()
    return [{"agent": r.agent_name, "count": r.count} for r in rows]


def get_top_tools(db: Session, days: int = 7, limit: int = 10) -> list[dict]:
    since = _since(days)
    q = (
        db.query(CTFEvent.tool_name, func.count(CTFEvent.id).label("count"))
        .filter(CTFEvent.tool_name.isnot(None))
    )
    if since:
        q = q.filter(CTFEvent.timestamp >= since)
    rows = q.group_by(CTFEvent.tool_name).order_by(func.count(CTFEvent.id).desc()).limit(limit).all()
    return [{"tool": r.tool_name, "count": r.count} for r in rows]


# ---------------------------------------------------------------------------
# Profile adoption
# ---------------------------------------------------------------------------

def get_profile_adoption(db: Session) -> dict:
    """Profile completion funnel — how many users have set up their identity."""
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_profiles = db.query(func.count(UserProfile.id)).scalar() or 0
    public = (
        db.query(func.count(UserProfile.id))
        .filter(UserProfile.is_public.is_(True))
        .scalar() or 0
    )
    with_username = (
        db.query(func.count(UserProfile.id))
        .filter(UserProfile.username.isnot(None))
        .scalar() or 0
    )
    with_bio = (
        db.query(func.count(UserProfile.id))
        .filter(UserProfile.bio.isnot(None), UserProfile.bio != "")
        .scalar() or 0
    )
    with_featured = (
        db.query(func.count(UserProfile.id))
        .filter(UserProfile.featured_badge_ids.isnot(None), UserProfile.featured_badge_ids != "[]")
        .scalar() or 0
    )
    show_activity = (
        db.query(func.count(UserProfile.id))
        .filter(UserProfile.show_activity.is_(True))
        .scalar() or 0
    )
    with_social = (
        db.query(func.count(UserProfile.id))
        .filter(
            (UserProfile.social_github.isnot(None))
            | (UserProfile.social_twitter.isnot(None))
            | (UserProfile.social_linkedin.isnot(None))
            | (UserProfile.social_hackerone.isnot(None))
            | (UserProfile.social_website.isnot(None))
        )
        .scalar() or 0
    )

    return {
        "total_users": total_users,
        "profiles_created": total_profiles,
        "public": public,
        "with_username": with_username,
        "with_bio": with_bio,
        "with_featured_badges": with_featured,
        "show_activity": show_activity,
        "with_social_links": with_social,
    }


# ---------------------------------------------------------------------------
# Share link stats (from PageView data)
# ---------------------------------------------------------------------------

def get_share_link_stats(db: Session, days: int = 7) -> dict:
    """Track hits on social share URLs from pageview data."""
    since = _since(days)

    def _count(path_prefix: str) -> int:
        q = db.query(func.count(PageView.id)).filter(
            PageView.path.like(f"{path_prefix}%")
        )
        if since:
            q = q.filter(PageView.timestamp >= since)
        return q.scalar() or 0

    profile_cards = _count("/ctf/share/profile/")
    badge_cards = _count("/ctf/share/badge/")
    public_profiles = _count("/ctf/api/v1/profile/u/")

    return {
        "profile_card_views": profile_cards,
        "badge_card_views": badge_cards,
        "public_profile_views": public_profiles,
        "total": profile_cards + badge_cards + public_profiles,
    }


# ---------------------------------------------------------------------------
# Session type breakdown for CTF players
# ---------------------------------------------------------------------------

def get_ctf_session_breakdown(db: Session) -> dict:
    """How many CTF players are authenticated vs temporary.

    Cross-references UserChallengeProgress.user_id against UserSession to
    determine session type. Uses the *most recent* session per user.
    """
    player_ids_q = (
        db.query(distinct(UserChallengeProgress.user_id))
        .subquery()
    )

    most_recent_session = (
        db.query(
            UserSession.user_id,
            UserSession.is_temporary,
        )
        .filter(UserSession.user_id.in_(db.query(player_ids_q)))
        .order_by(UserSession.user_id, UserSession.last_accessed.desc())
        .all()
    )

    seen = set()
    perm = 0
    temp = 0
    for row in most_recent_session:
        if row.user_id in seen:
            continue
        seen.add(row.user_id)
        if row.is_temporary:
            temp += 1
        else:
            perm += 1

    total = perm + temp
    return {
        "perm": perm,
        "temp": temp,
        "total": total,
    }
