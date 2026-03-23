"""Share Routes - OG image generation for social sharing via Playwright."""

import base64
import hashlib
import io
import logging
from pathlib import Path

import httpx
import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from finbot.apps.ctf.rendering import get_renderer
from finbot.config import settings
from finbot.core.data.database import get_db
from finbot.core.data.models import UserBadge, UserChallengeProgress
from finbot.core.data.repositories import (
    BadgeRepository,
    ChallengeRepository,
    UserProfileRepository,
)

from .profile import calculate_level, resolve_avatar_url, xp_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share", tags=["share"])

CACHE_DIR = (
    Path(settings.DATA_DIR if hasattr(settings, "DATA_DIR") else ".")
    / "cache"
    / "share_cards"
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "share"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)

RARITY_COLORS_HEX = {
    "common": "#64748b",
    "rare": "#3b82f6",
    "epic": "#a855f7",
    "legendary": "#fbbf24",
}

_STATIC_IMAGES = (
    Path(__file__).parent.parent.parent.parent / "static" / "images" / "common"
)
_BADGE_IMAGES = (
    Path(__file__).parent.parent.parent.parent / "static" / "images" / "ctf" / "badges"
)
_b64_cache: dict[str, str] = {}


def _get_image_b64(filename: str) -> str:
    """Load a static image as a base64 string (cached after first call)."""
    if filename in _b64_cache:
        return _b64_cache[filename]

    try:
        _b64_cache[filename] = base64.b64encode(
            (_STATIC_IMAGES / filename).read_bytes()
        ).decode()
    except (OSError, IOError):
        _b64_cache[filename] = ""
    return _b64_cache[filename]


def _get_badge_image_b64(filename: str) -> str:
    """Load a badge image as a base64 data URI (cached after first call)."""
    cache_key = f"badge:{filename}"
    if cache_key in _b64_cache:
        return _b64_cache[cache_key]

    try:
        raw = (_BADGE_IMAGES / filename).read_bytes()
        _b64_cache[cache_key] = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
    except (OSError, IOError):
        _b64_cache[cache_key] = ""
    return _b64_cache[cache_key]


def get_cache_path(cache_key: str) -> Path:
    """Get cache file path for a given key."""
    return CACHE_DIR / f"{cache_key}.png"


async def _fetch_avatar_b64(url: str) -> str:
    """Fetch a remote avatar image and return it as a base64 data URI.

    Returns empty string on any failure (timeout, bad content type, too large).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return ""
            if len(resp.content) > 2 * 1024 * 1024:
                return ""
            mime = content_type.split(";")[0].strip()
            return f"data:{mime};base64,{base64.b64encode(resp.content).decode()}"
    except Exception:
        logger.debug("Failed to fetch avatar from %s", url, exc_info=True)
        return ""


def _badge_template_context(badge: object) -> dict:
    """Build shared template context for badge cards."""
    rarity_color = RARITY_COLORS_HEX.get(badge.rarity, "#64748b")
    show_rays = badge.rarity in ("rare", "epic", "legendary")
    num_rays = 12 if badge.rarity == "legendary" else 8
    ray_angles = [int(360 * i / num_rays) for i in range(num_rays)] if show_rays else []

    desc = badge.description or ""
    if len(desc) > 80:
        desc = desc[:77] + "..."

    badge_image_b64 = ""
    icon_url = getattr(badge, "icon_url", None)
    if icon_url:
        badge_image_b64 = _get_badge_image_b64(icon_url)

    return {
        "badge_icon": badge.title[0].upper() if badge.title else "?",
        "badge_image_b64": badge_image_b64,
        "badge_title": badge.title,
        "badge_description": desc,
        "badge_points": badge.points,
        "rarity_label": badge.rarity.upper(),
        "rarity_color": rarity_color,
        "is_secret": getattr(badge, "is_secret", False),
        "show_rays": show_rays,
        "ray_angles": ray_angles,
        "logo_b64": _get_image_b64("finbot.png"),
        "owasp_logo_b64": _get_image_b64("GenAI_OWASP_Logo.png"),
    }


_xp_progress = xp_progress


def _make_qr_data_uri(url: str, dark: str = "#64748b") -> str:
    """Generate a QR code as an SVG data URI suitable for embedding in HTML."""
    qr = segno.make(url)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", xmldecl=False, border=0, dark=dark, light=None)
    svg_bytes = buf.getvalue()
    return f"data:image/svg+xml;base64,{base64.b64encode(svg_bytes).decode()}"


def _profile_url(request: Request, username: str) -> str:
    """Build the public profile URL from the current request."""
    return f"{request.base_url}ctf/h/{username}"


def _render_html(template_name: str, context: dict) -> str:
    """Render a share-card Jinja2 template to an HTML string."""
    template = _jinja_env.get_template(template_name)
    return template.render(**context)


async def _render_card(template_name: str, context: dict) -> bytes:
    """Render an HTML share-card template to PNG via Playwright."""
    html = _render_html(template_name, context)
    return await get_renderer().render_to_png(html)


# ---------------------------------------------------------------------------
# Profile card
# ---------------------------------------------------------------------------


@router.get("/profile/{username}/card.png")
async def get_profile_card(
    request: Request,
    username: str,
    db: Session = Depends(get_db),
    html: bool = Query(
        False, description="Return raw HTML instead of PNG (debug mode)"
    ),
):
    """Generate and return a profile share card image."""
    profile_repo = UserProfileRepository(db)
    profile, user = profile_repo.get_public_profile_with_user(username)

    if not profile or not user:
        raise HTTPException(status_code=404, detail="Profile not found")

    completed_progress = (
        db.query(UserChallengeProgress)
        .filter(
            UserChallengeProgress.namespace == user.namespace,
            UserChallengeProgress.user_id == profile.user_id,
            UserChallengeProgress.status == "completed",
        )
        .all()
    )

    earned_badges = (
        db.query(UserBadge)
        .filter(
            UserBadge.namespace == user.namespace,
            UserBadge.user_id == profile.user_id,
        )
        .all()
    )

    challenge_repo = ChallengeRepository(db)
    badge_repo = BadgeRepository(db)

    challenge_points = challenge_repo.get_effective_points(completed_progress)
    earned_badge_ids = [b.badge_id for b in earned_badges]
    badge_points = badge_repo.get_total_points(earned_badge_ids)
    hints_cost = sum(p.hints_cost for p in completed_progress)
    total_points = challenge_points + badge_points - hints_cost

    level, level_title = calculate_level(total_points)
    xp = _xp_progress(total_points)

    # Featured badges (user-curated, up to 6)
    featured_badges: list[dict] = []
    featured_ids = profile.get_featured_badge_ids()
    if featured_ids:
        earned_set = set(earned_badge_ids)
        for bid in featured_ids:
            if bid in earned_set:
                badge = badge_repo.get_badge(bid)
                if badge:
                    featured_badges.append(
                        {"title": badge.title, "rarity": badge.rarity, "is_secret": badge.is_secret}
                    )

    # Latest badge
    latest_badge_title = ""
    if earned_badges:
        most_recent = max(earned_badges, key=lambda b: b.earned_at)
        badge_obj = badge_repo.get_badge(most_recent.badge_id)
        if badge_obj:
            latest_badge_title = badge_obj.title

    member_since = ""
    if profile.created_at:
        member_since = profile.created_at.strftime("%b %Y")

    bio = profile.bio or "AI Security Enthusiast"

    # Resolve avatar image for the card
    avatar_image_b64 = ""
    avatar_url = resolve_avatar_url(profile, user)
    if avatar_url:
        avatar_image_b64 = await _fetch_avatar_b64(avatar_url)

    profile_link = _profile_url(request, profile.username)
    qr_data_uri = _make_qr_data_uri(profile_link)

    template_context = {
        "username": profile.username,
        "avatar_emoji": profile.avatar_emoji or "",
        "avatar_image_b64": avatar_image_b64,
        "bio": bio,
        "level": level,
        "level_title": level_title,
        "total_points": total_points,
        "badges_earned": len(earned_badges),
        "challenges_completed": len(completed_progress),
        **xp,
        "featured_badges": featured_badges,
        "latest_badge_title": latest_badge_title,
        "member_since": member_since,
        "rarity_colors": RARITY_COLORS_HEX,
        "logo_b64": _get_image_b64("finbot.png"),
        "owasp_logo_b64": _get_image_b64("GenAI_OWASP_Logo.png"),
        "qr_data_uri": qr_data_uri,
    }

    if html and settings.DEBUG:
        return HTMLResponse(_render_html("profile_card.html", template_context))

    cache_data = (
        f"{username}:{total_points}:{len(earned_badges)}:{len(completed_progress)}"
    )
    cache_key = hashlib.md5(cache_data.encode()).hexdigest()
    cache_path = get_cache_path(cache_key)

    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=300"},
        )

    image_bytes = await _render_card("profile_card.html", template_context)

    cache_path.write_bytes(image_bytes)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ---------------------------------------------------------------------------
# User badge card (personalized)
# ---------------------------------------------------------------------------


@router.get("/badge/{username}/{badge_id}/card.png")
async def get_user_badge_card(
    request: Request,
    username: str,
    badge_id: str,
    db: Session = Depends(get_db),
    html: bool = Query(
        False, description="Return raw HTML instead of PNG (debug mode)"
    ),
):
    """Generate a personalized badge card showing the user earned this badge."""
    profile_repo = UserProfileRepository(db)
    profile, user = profile_repo.get_public_profile_with_user(username)

    if not profile or not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_badge = (
        db.query(UserBadge)
        .filter(
            UserBadge.namespace == user.namespace,
            UserBadge.user_id == profile.user_id,
            UserBadge.badge_id == badge_id,
        )
        .first()
    )

    if not user_badge:
        raise HTTPException(status_code=404, detail="User has not earned this badge")

    badge_repo = BadgeRepository(db)
    badge = badge_repo.get_badge(badge_id)

    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")

    context = _badge_template_context(badge)
    context["username"] = username
    context["qr_data_uri"] = _make_qr_data_uri(
        _profile_url(request, username), dark=context["rarity_color"]
    )

    if html and settings.DEBUG:
        return HTMLResponse(_render_html("user_badge_card.html", context))

    image_bytes = await _render_card("user_badge_card.html", context)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )
