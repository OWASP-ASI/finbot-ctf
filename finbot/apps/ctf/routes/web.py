"""CTF Portal Web Routes"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import (
    get_authenticated_session_context,
    get_session_context,
)
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    UserProfileRepository,
)
from finbot.core.templates import TemplateResponse

from .profile import calculate_level

# Setup templates
template_response = TemplateResponse("finbot/apps/ctf/templates")

# Create web router
router = APIRouter(tags=["ctf-web"])


@router.get("/", name="ctf_root")
async def ctf_root():
    """Redirect /ctf to /ctf/dashboard"""
    return RedirectResponse(url="/ctf/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse, name="ctf_dashboard")
async def ctf_dashboard(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """CTF Dashboard page"""
    return template_response(
        request,
        "pages/dashboard.html",
        {"session_context": session_context},
    )


@router.get("/challenges", response_class=HTMLResponse, name="ctf_challenges")
async def ctf_challenges(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """CTF Challenges list page"""
    return template_response(
        request,
        "pages/challenges.html",
        {"session_context": session_context},
    )


@router.get(
    "/challenges/{challenge_id}", response_class=HTMLResponse, name="ctf_challenge"
)
async def ctf_challenge(
    request: Request,
    challenge_id: str,
    session_context: SessionContext = Depends(get_session_context),
):
    """CTF Challenge detail page"""
    return template_response(
        request,
        "pages/challenge.html",
        {
            "challenge_id": challenge_id,
            "session_context": session_context,
        },
    )


@router.get("/activity", response_class=HTMLResponse, name="ctf_activity")
async def ctf_activity(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """CTF Activity stream page"""
    return template_response(
        request,
        "pages/activity.html",
        {"session_context": session_context},
    )


@router.get("/badges", response_class=HTMLResponse, name="ctf_badges")
async def ctf_badges(
    request: Request, session_context: SessionContext = Depends(get_session_context)
):
    """CTF Badges page"""
    return template_response(
        request,
        "pages/badges.html",
        {"session_context": session_context},
    )


@router.get(
    "/profile/settings", response_class=HTMLResponse, name="ctf_profile_settings"
)
async def ctf_profile_settings(
    request: Request,
    session_context: SessionContext = Depends(get_authenticated_session_context),
):
    """Profile settings page - requires authenticated session"""
    return template_response(
        request,
        "pages/profile_settings.html",
        {"session_context": session_context},
    )


@router.get("/h/{username}", response_class=HTMLResponse, name="ctf_public_profile")
async def ctf_public_profile(
    request: Request,
    username: str,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Public profile page - viewable by anyone"""
    # Fetch basic profile data for OG meta tags
    profile_repo = UserProfileRepository(db)
    profile, user = profile_repo.get_public_profile_with_user(username)

    # OG meta data (defaults if profile not found)
    og_data = {
        "og_title": f"@{username} - OWASP FinBot CTF Hacker Profile",
        "og_description": "Check out this hacker's profile on OWASP FinBot CTF - Agentic AI Security Capture The Flag",
        "og_image": f"{request.base_url}ctf/share/profile/{username}/card.png",
        "og_url": str(request.url),
    }

    if profile and user:
        from finbot.core.data.models import UserBadge, UserChallengeProgress

        challenge_repo = ChallengeRepository(db)
        badge_repo = BadgeRepository(db)

        completed_progress = (
            db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == user.namespace,
                UserChallengeProgress.user_id == profile.user_id,
                UserChallengeProgress.status == "completed",
            )
            .all()
        )
        earned_badge_ids = [
            b.badge_id
            for b in db.query(UserBadge)
            .filter(
                UserBadge.namespace == user.namespace,
                UserBadge.user_id == profile.user_id,
            )
            .all()
        ]

        completed_count = len(completed_progress)
        badge_count = len(earned_badge_ids)
        total_points = (
            challenge_repo.get_effective_points(completed_progress)
            + badge_repo.get_total_points(earned_badge_ids)
            - sum(p.hints_cost for p in completed_progress)
        )
        level, level_title = calculate_level(total_points)
        bio = profile.bio or "AI Security Enthusiast"

        og_data["og_title"] = f"@{username} · {level_title} | FinBot CTF"
        og_data["og_description"] = (
            f"{bio} | {completed_count} challenges · {badge_count} badges"
        )

    return template_response(
        request,
        "pages/public_profile.html",
        {
            "username": username,
            "session_context": session_context,
            **og_data,
        },
    )
