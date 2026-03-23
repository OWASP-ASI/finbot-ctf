"""CC Users — user management and session admin"""

# pylint: disable=not-callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from sqlalchemy import func

from finbot.core.data.database import SessionLocal
from finbot.core.data.models import (
    Badge,
    ChatMessage,
    CTFEvent,
    User,
    UserBadge,
    UserChallengeProgress,
    UserProfile,
    UserSession,
)
from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/users")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _user_list(db, search: str | None = None) -> list[dict]:
    """Get all users with summary stats."""
    q = db.query(User).order_by(User.created_at.desc())
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            (User.email.ilike(pattern))
            | (User.display_name.ilike(pattern))
            | (User.user_id.ilike(pattern))
        )
    users = q.limit(200).all()

    result = []
    for u in users:
        latest_session = (
            db.query(UserSession)
            .filter(UserSession.user_id == u.user_id)
            .order_by(UserSession.last_accessed.desc())
            .first()
        )

        completed = (
            db.query(func.count(UserChallengeProgress.id))
            .filter(
                UserChallengeProgress.user_id == u.user_id,
                UserChallengeProgress.status == "completed",
            )
            .scalar() or 0
        )
        attempted = (
            db.query(func.count(UserChallengeProgress.id))
            .filter(UserChallengeProgress.user_id == u.user_id)
            .scalar() or 0
        )
        badges = (
            db.query(func.count(UserBadge.id))
            .filter(UserBadge.user_id == u.user_id)
            .scalar() or 0
        )
        has_profile = (
            db.query(UserProfile)
            .filter(UserProfile.user_id == u.user_id)
            .first() is not None
        )

        result.append({
            "user_id": u.user_id,
            "email": u.email,
            "display_name": u.display_name,
            "namespace": u.namespace,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login": u.last_login,
            "has_profile": has_profile,
            "completed": completed,
            "attempted": attempted,
            "badges": badges,
            "session_type": "perm" if latest_session and not latest_session.is_temporary else "temp" if latest_session else None,
            "last_active": latest_session.last_accessed if latest_session else u.last_login,
        })

    return result


def _user_detail(db, user_id: str) -> dict | None:
    """Full detail view for one user. Returns plain dicts safe to use after db.close()."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None

    profile_row = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    sessions_rows = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.last_accessed.desc())
        .all()
    )

    progress_rows = (
        db.query(UserChallengeProgress)
        .filter(UserChallengeProgress.user_id == user_id)
        .order_by(UserChallengeProgress.status.desc(), UserChallengeProgress.challenge_id)
        .all()
    )

    badges_rows = (
        db.query(UserBadge, Badge.title, Badge.rarity)
        .join(Badge, UserBadge.badge_id == Badge.id)
        .filter(UserBadge.user_id == user_id)
        .order_by(UserBadge.earned_at.desc())
        .all()
    )

    events_rows = (
        db.query(CTFEvent)
        .filter(CTFEvent.user_id == user_id)
        .order_by(CTFEvent.timestamp.desc())
        .limit(20)
        .all()
    )

    event_count = (
        db.query(func.count(CTFEvent.id))
        .filter(CTFEvent.user_id == user_id)
        .scalar() or 0
    )
    chat_count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.user_id == user_id)
        .scalar() or 0
    )

    user_dict = {
        "user_id": user.user_id, "email": user.email,
        "display_name": user.display_name, "namespace": user.namespace,
        "is_active": user.is_active, "created_at": user.created_at,
        "last_login": user.last_login,
    }

    profile_dict = None
    if profile_row:
        profile_dict = {
            "username": profile_row.username, "bio": profile_row.bio,
            "avatar_emoji": profile_row.avatar_emoji,
            "avatar_type": profile_row.avatar_type,
            "is_public": profile_row.is_public,
            "show_activity": profile_row.show_activity,
        }

    sessions = [
        {"session_id": s.session_id, "is_temporary": s.is_temporary,
         "last_accessed": s.last_accessed, "expires_at": s.expires_at,
         "current_ip": s.current_ip, "original_ip": s.original_ip}
        for s in sessions_rows
    ]

    progress = [
        {"challenge_id": p.challenge_id, "status": p.status,
         "attempts": p.attempts, "hints_used": p.hints_used,
         "completed_at": p.completed_at}
        for p in progress_rows
    ]

    badges_earned = [
        {"badge_id": ub.UserBadge.badge_id, "title": ub.title,
         "rarity": ub.rarity, "earned_at": ub.UserBadge.earned_at}
        for ub in badges_rows
    ]

    recent_events = [
        {"event_type": e.event_type, "summary": e.summary,
         "severity": e.severity, "timestamp": e.timestamp}
        for e in events_rows
    ]

    return {
        "target_user": user_dict,
        "profile": profile_dict,
        "sessions": sessions,
        "progress": progress,
        "badges_earned": badges_earned,
        "recent_events": recent_events,
        "counts": {
            "sessions": len(sessions),
            "completed": sum(1 for p in progress if p["status"] == "completed"),
            "attempted": len(progress),
            "badges": len(badges_earned),
            "events": event_count,
            "chats": chat_count,
        },
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def users_list(request: Request, search: str = Query(default="")):
    """User list with search"""
    db = SessionLocal()
    try:
        users = _user_list(db, search=search if search else None)
        total_users = db.query(func.count(User.id)).scalar() or 0
        data = {
            "users": users,
            "total_users": total_users,
            "search": search,
        }
    finally:
        db.close()
    return template_response(request, "pages/users.html", data)


@router.get("/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: str):
    """User detail view"""
    db = SessionLocal()
    try:
        data = _user_detail(db, user_id)
        if not data:
            raise HTTPException(status_code=404, detail="User not found")
    finally:
        db.close()
    return template_response(request, "pages/user_detail.html", data)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@router.post("/api/{user_id}/kill-sessions")
async def kill_sessions(user_id: str):
    """Delete all sessions for a user (force logout)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        count = db.query(UserSession).filter(UserSession.user_id == user_id).delete()
        db.commit()
        return {"action": "kill_sessions", "user_id": user_id, "deleted": count}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/api/{user_id}/delete-profile")
async def delete_profile(user_id: str):
    """Delete the user's profile."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        count = db.query(UserProfile).filter(UserProfile.user_id == user_id).delete()
        db.commit()
        return {"action": "delete_profile", "user_id": user_id, "deleted": count}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/api/{user_id}/toggle-active")
async def toggle_active(user_id: str):
    """Toggle user active status. Deactivation also kills all sessions."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = not user.is_active
        sessions_killed = 0
        if not user.is_active:
            sessions_killed = db.query(UserSession).filter(UserSession.user_id == user_id).delete()
        db.commit()
        return {
            "action": "toggle_active", "user_id": user_id,
            "is_active": user.is_active, "sessions_killed": sessions_killed,
        }
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/api/{user_id}/full-ctf-reset")
async def full_ctf_reset(user_id: str, confirm_user_id: str = Query(...)):
    """Full CTF reset: wipes progress, badges, events, and chat.
    Requires confirm_user_id to match as a safety check.
    """
    if confirm_user_id != user_id:
        raise HTTPException(status_code=400, detail="Confirmation user_id does not match")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        deleted = {}
        deleted["progress"] = db.query(UserChallengeProgress).filter(
            UserChallengeProgress.user_id == user_id
        ).delete()
        deleted["badges"] = db.query(UserBadge).filter(
            UserBadge.user_id == user_id
        ).delete()
        deleted["events"] = db.query(CTFEvent).filter(
            CTFEvent.user_id == user_id
        ).delete()
        deleted["chat"] = db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id
        ).delete()
        deleted["sessions"] = db.query(UserSession).filter(
            UserSession.user_id == user_id
        ).delete()

        db.commit()
        return {"action": "full_ctf_reset", "user_id": user_id, "deleted": deleted}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
