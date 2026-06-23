"""Profile API Routes - Social features for authenticated users"""

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_authenticated_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    UserBadgeRepository,
    UserProfileRepository,
    validate_username,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


# =============================================================================
# Level System
# =============================================================================

LEVEL_THRESHOLDS = [
    (10000, 10, "Elite Hacker"),
    (7500, 9, "Master Exploiter"),
    (5000, 8, "Senior Pentester"),
    (3500, 7, "Security Researcher"),
    (2500, 6, "Vulnerability Hunter"),
    (1500, 5, "Exploit Developer"),
    (1000, 4, "Red Teamer"),
    (500, 3, "Bug Hunter"),
    (200, 2, "Apprentice"),
    (0, 1, "Script Kiddie"),
]


def calculate_level(points: int) -> tuple[int, str]:
    """Calculate level and title based on points.
    
    Returns (level_number, level_title).
    """
    for threshold, level, title in LEVEL_THRESHOLDS:
        if points >= threshold:
            return level, title
    return 1, "Script Kiddie"


def xp_progress(total_points: int) -> dict:
    """Compute XP progress toward the next level."""
    current_threshold = 0
    next_threshold = LEVEL_THRESHOLDS[0][0]
    next_title = "Max Level"

    for i, (threshold, _level, _title) in enumerate(LEVEL_THRESHOLDS):
        if total_points >= threshold:
            current_threshold = threshold
            if i > 0:
                next_threshold = LEVEL_THRESHOLDS[i - 1][0]
                next_title = LEVEL_THRESHOLDS[i - 1][2]
            else:
                next_threshold = threshold
                next_title = _title
            break

    span = max(next_threshold - current_threshold, 1)
    progress = min(int(((total_points - current_threshold) / span) * 100), 100)

    return {
        "xp_current": total_points,
        "xp_next_threshold": next_threshold,
        "xp_next_title": next_title,
        "xp_pct": progress,
    }


VALID_AVATAR_TYPES = ("emoji", "gravatar", "url")


def gravatar_url(email: str, size: int = 256) -> str:
    """Build a Gravatar URL from an email address."""
    h = hashlib.md5(email.lower().strip().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{h}?s={size}&d=retro"


def resolve_avatar_url(profile, user=None) -> str | None:
    """Resolve the effective avatar URL for a profile.

    Returns a URL string for gravatar/url types, or None for emoji.
    """
    avatar_type = profile.avatar_type or "emoji"
    if avatar_type == "gravatar" and user and user.email:
        return gravatar_url(user.email)
    if avatar_type == "url" and profile.avatar_url:
        return profile.avatar_url
    return None


# =============================================================================
# Response Models
# =============================================================================


class SocialLinksResponse(BaseModel):
    """Social links in API responses"""

    github: str | None = None
    hackerone: str | None = None
    bugcrowd: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    website: str | None = None


class ProfileResponse(BaseModel):
    """User's own profile response"""

    user_id: str
    username: str | None
    bio: str | None
    avatar_emoji: str
    avatar_type: str
    avatar_url: str | None
    gravatar_preview_url: str | None
    is_public: bool
    show_activity: bool
    featured_badge_ids: list[str]
    created_at: str
    has_username: bool
    social_links: SocialLinksResponse | None = None


class SocialLinksUpdate(BaseModel):
    """Nested social links object sent by the frontend"""

    github: HttpUrl | None = None
    hackerone: HttpUrl | None = None
    bugcrowd: HttpUrl | None = None
    twitter: HttpUrl | None = None
    linkedin: HttpUrl | None = None
    website: HttpUrl | None = None


class ProfileUpdateRequest(BaseModel):
    """Profile update request"""

    username: str | None = Field(None, min_length=3, max_length=20)
    bio: str | None = Field(None, max_length=300)
    avatar_emoji: str | None = Field(None, max_length=10)
    avatar_type: str | None = Field(None, pattern="^(emoji|gravatar|url)$")
    avatar_url: str | None = Field(None, max_length=500)
    is_public: bool | None = None
    show_activity: bool | None = None
    social_links: SocialLinksUpdate | None = None


class FeaturedBadgesRequest(BaseModel):
    """Featured badges update request"""

    badge_ids: list[str] = Field(..., max_length=6)


class UsernameCheckResponse(BaseModel):
    """Username availability check response"""

    username: str
    available: bool
    error: str | None = None


class BadgeSummary(BaseModel):
    """Badge summary for public profile"""

    id: str
    title: str
    description: str | None
    rarity: str
    points: int
    is_secret: bool
    icon_url: str | None


class CategoryProgress(BaseModel):
    """Category progress for public profile"""

    category: str
    percentage: int


class RecentAchievement(BaseModel):
    """Recent achievement for activity feed"""

    type: str  # "badge" or "challenge"
    title: str
    description: str | None
    rarity: str | None  # For badges
    earned_at: str


class PublicProfileResponse(BaseModel):
    """Public profile response"""

    username: str
    display_name: str | None
    bio: str | None
    avatar_emoji: str
    avatar_type: str
    avatar_url: str | None
    member_since: str

    # Level
    level: int
    level_title: str

    # XP progress
    xp_current: int
    xp_next_threshold: int
    xp_next_title: str
    xp_pct: int

    # Stats
    total_points: int
    challenges_completed: int
    challenges_total: int
    badges_earned: int
    completion_percentage: int

    # Featured badges
    featured_badges: list[BadgeSummary]

    # Category mastery
    category_progress: list[CategoryProgress]

    # Recent achievements (if show_activity is True)
    show_activity: bool
    recent_achievements: list[RecentAchievement]

    # Social links
    social_links: SocialLinksResponse | None = None


SOCIAL_PLATFORMS = ["github", "hackerone", "bugcrowd", "twitter", "linkedin", "website"]


def _build_social_links(profile) -> SocialLinksResponse | None:
    """Build social_links from individual profile columns."""
    links = {}
    for platform in SOCIAL_PLATFORMS:
        value = getattr(profile, f"social_{platform}", None)
        if value:
            links[platform] = value
    return SocialLinksResponse(**links) if links else None


def _update_social_links(profile, request, db) -> None:
    """Flatten social_links from request into individual profile columns."""
    update_data = request.model_dump(exclude_unset=True)
    if "social_links" not in update_data:
        return

    links = update_data["social_links"] or {}

    for platform in SOCIAL_PLATFORMS:
        value = links.get(platform)
        setattr(profile, f"social_{platform}", str(value) if value else None)

    db.commit()
    db.refresh(profile)


def _build_profile_response(profile, user) -> ProfileResponse:
    """Build a ProfileResponse from a profile and user."""
    grav_preview = gravatar_url(user.email) if user and user.email else None
    return ProfileResponse(
        user_id=profile.user_id,
        username=profile.username,
        bio=profile.bio,
        avatar_emoji=profile.avatar_emoji or "🦊",
        avatar_type=profile.avatar_type or "emoji",
        avatar_url=resolve_avatar_url(profile, user),
        gravatar_preview_url=grav_preview,
        is_public=profile.is_public,
        show_activity=profile.show_activity,
        featured_badge_ids=profile.get_featured_badge_ids(),
        created_at=profile.created_at.isoformat().replace("+00:00", "Z"),
        has_username=profile.username is not None,
        social_links=_build_social_links(profile),
    )


# =============================================================================
# Authenticated Endpoints (require permanent session)
# =============================================================================


@router.get("", response_model=ProfileResponse)
async def get_own_profile(
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Get the current user's profile"""
    profile_repo = UserProfileRepository(db, session_context)
    profile = profile_repo.get_or_create_for_current_user()

    from finbot.core.data.models import User
    user = db.query(User).filter(User.user_id == profile.user_id).first()

    return _build_profile_response(profile, user)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    request: ProfileUpdateRequest,
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Update the current user's profile"""
    profile_repo = UserProfileRepository(db, session_context)

    # Handle username change separately (needs validation)
    if request.username is not None:
        is_valid, error = validate_username(request.username)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)

        if not profile_repo.is_username_available(
            request.username, exclude_user_id=session_context.user_id
        ):
            raise HTTPException(status_code=400, detail="Username is already taken")

        profile, error = profile_repo.claim_username(
            session_context.user_id, request.username
        )
        if error:
            raise HTTPException(status_code=400, detail=error)

    # Validate avatar_url if switching to url type
    if request.avatar_type == "url" and request.avatar_url:
        if not request.avatar_url.startswith("https://"):
            raise HTTPException(status_code=400, detail="Avatar URL must use HTTPS")

    # Update other fields
    profile = profile_repo.update_profile(
        user_id=session_context.user_id,
        bio=request.bio,
        avatar_emoji=request.avatar_emoji,
        avatar_type=request.avatar_type,
        avatar_url=request.avatar_url,
        is_public=request.is_public,
        show_activity=request.show_activity,
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _update_social_links(profile, request, db)

    from finbot.core.data.models import User
    user = db.query(User).filter(User.user_id == profile.user_id).first()

    return _build_profile_response(profile, user)


@router.put("/featured-badges", response_model=ProfileResponse)
async def set_featured_badges(
    request: FeaturedBadgesRequest,
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Set featured badges for the profile (max 6)"""
    profile_repo = UserProfileRepository(db, session_context)

    # Validate that the user actually has these badges
    user_badge_repo = UserBadgeRepository(db, session_context)
    earned_ids = user_badge_repo.get_earned_badge_ids()

    valid_badge_ids = [bid for bid in request.badge_ids if bid in earned_ids]

    profile = profile_repo.set_featured_badges(session_context.user_id, valid_badge_ids)

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    from finbot.core.data.models import User
    user = db.query(User).filter(User.user_id == profile.user_id).first()

    return _build_profile_response(profile, user)


@router.get("/check-username/{username}", response_model=UsernameCheckResponse)
async def check_username_availability(
    username: str,
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Check if a username is available"""
    is_valid, error = validate_username(username)

    if not is_valid:
        return UsernameCheckResponse(username=username, available=False, error=error)

    profile_repo = UserProfileRepository(db, session_context)
    available = profile_repo.is_username_available(
        username, exclude_user_id=session_context.user_id
    )

    return UsernameCheckResponse(
        username=username,
        available=available,
        error=None if available else "Username is already taken",
    )


# =============================================================================
# Public Endpoints (no auth required)
# =============================================================================


@router.get("/u/{username}", response_model=PublicProfileResponse)
async def get_public_profile(
    username: str,
    db: Session = Depends(get_db),
):
    """Get a public profile by username"""
    profile_repo = UserProfileRepository(db)
    profile, user = profile_repo.get_public_profile_with_user(username)

    if not profile or not user:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Build a minimal session context for the profile owner to query their stats
    # We need to query their data without being logged in as them
    owner_namespace = user.namespace

    # Get their stats using their namespace
    challenge_repo = ChallengeRepository(db)
    badge_repo = BadgeRepository(db)

    # Load all progress rows for consistent profile stats with /api/v1/stats.
    from finbot.core.data.models import UserChallengeProgress, UserBadge

    all_progress = (
        db.query(UserChallengeProgress)
        .filter(
            UserChallengeProgress.namespace == owner_namespace,
            UserChallengeProgress.user_id == profile.user_id,
        )
        .all()
    )
    completed_progress = [p for p in all_progress if p.status == "completed"]
    hints_cost = sum(p.hints_cost for p in all_progress)

    # Get badge data
    earned_badges = (
        db.query(UserBadge)
        .filter(
            UserBadge.namespace == owner_namespace,
            UserBadge.user_id == profile.user_id,
        )
        .all()
    )
    earned_badge_ids = [b.badge_id for b in earned_badges]

    # Calculate points
    challenge_points = challenge_repo.get_effective_points(completed_progress)
    badge_points = badge_repo.get_total_points(earned_badge_ids)
    total_points = challenge_points + badge_points - hints_cost

    # Get totals
    total_challenges = len(challenge_repo.list_challenges())

    # Completion percentage
    completion_pct = (
        int((len(completed_progress) / total_challenges) * 100)
        if total_challenges > 0
        else 0
    )

    # Category progress
    category_counts = challenge_repo.count_by_category()
    challenges = challenge_repo.list_challenges()
    completed_ids = {p.challenge_id for p in completed_progress}

    category_progress = []
    for cat, total in category_counts.items():
        completed_in_cat = sum(
            1 for c in challenges if c.category == cat and c.id in completed_ids
        )
        category_progress.append(
            CategoryProgress(
                category=cat,
                percentage=int((completed_in_cat / total) * 100) if total > 0 else 0,
            )
        )

    # Featured badges
    featured_badge_ids = profile.get_featured_badge_ids()
    featured_badges = []

    if featured_badge_ids:
        for badge_id in featured_badge_ids:
            if badge_id in earned_badge_ids:
                badge = badge_repo.get_badge(badge_id)
                if badge:
                    featured_badges.append(
                        BadgeSummary(
                            id=badge.id,
                            title=badge.title,
                            description=badge.description,
                            rarity=badge.rarity,
                            points=badge.points,
                            is_secret=badge.is_secret,
                            icon_url=badge.icon_url,
                        )
                    )

    # If no featured badges set, use recent earned badges
    if not featured_badges and earned_badges:
        recent_badges = sorted(earned_badges, key=lambda b: b.earned_at, reverse=True)[
            :6
        ]
        for ub in recent_badges:
            badge = badge_repo.get_badge(ub.badge_id)
            if badge:
                featured_badges.append(
                    BadgeSummary(
                        id=badge.id,
                        title=badge.title,
                        description=badge.description,
                        rarity=badge.rarity,
                        points=badge.points,
                        is_secret=badge.is_secret,
                        icon_url=badge.icon_url,
                    )
                )

    # Calculate level and XP progress
    level, level_title = calculate_level(total_points)
    xp = xp_progress(total_points)

    # Recent achievements (if show_activity is enabled)
    recent_achievements: list[RecentAchievement] = []
    if profile.show_activity:
        # Get recent badges (last 5)
        recent_earned_badges = sorted(
            earned_badges, key=lambda b: b.earned_at, reverse=True
        )[:5]
        for ub in recent_earned_badges:
            badge = badge_repo.get_badge(ub.badge_id)
            if badge:
                recent_achievements.append(
                    RecentAchievement(
                        type="badge",
                        title=badge.title,
                        description=badge.description,
                        rarity=badge.rarity,
                        earned_at=ub.earned_at.isoformat().replace("+00:00", "Z"),
                    )
                )

        # Get recent challenge completions (last 5)
        recent_challenges = sorted(
            completed_progress, key=lambda p: p.completed_at or p.updated_at, reverse=True
        )[:5]
        for prog in recent_challenges:
            challenge = challenge_repo.get_challenge(prog.challenge_id)
            if challenge:
                completed_time = prog.completed_at or prog.updated_at
                recent_achievements.append(
                    RecentAchievement(
                        type="challenge",
                        title=challenge.title,
                        description=f"{challenge.difficulty.capitalize()} · {challenge.points} pts",
                        rarity=None,
                        earned_at=completed_time.isoformat().replace("+00:00", "Z"),
                    )
                )

        # Sort by date and take top 6
        recent_achievements.sort(key=lambda a: a.earned_at, reverse=True)
        recent_achievements = recent_achievements[:6]

    return PublicProfileResponse(
        username=profile.username,
        display_name=user.display_name,
        bio=profile.bio,
        avatar_emoji=profile.avatar_emoji or "🦊",
        avatar_type=profile.avatar_type or "emoji",
        avatar_url=resolve_avatar_url(profile, user),
        member_since=user.created_at.isoformat().replace("+00:00", "Z"),
        level=level,
        level_title=level_title,
        **xp,
        total_points=total_points,
        challenges_completed=len(completed_progress),
        challenges_total=total_challenges,
        badges_earned=len(earned_badge_ids),
        completion_percentage=completion_pct,
        featured_badges=featured_badges,
        category_progress=category_progress,
        show_activity=profile.show_activity,
        recent_achievements=recent_achievements,
        social_links=_build_social_links(profile),
    )
