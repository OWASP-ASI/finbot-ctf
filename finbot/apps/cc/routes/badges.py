"""CC Badges — read-only viewer + ops tool for badge definitions"""

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from finbot.core.data.database import SessionLocal
from finbot.core.data.models import Badge, UserBadge
from finbot.core.templates import TemplateResponse
from finbot.ctf.evaluators.registry import list_registered_evaluators

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/badges")

RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
CATEGORY_DISPLAY = {
    "achievement": "Achievement",
    "milestone": "Milestone",
    "special": "Special",
}


def _badge_list_with_stats(db) -> list[dict]:
    """Get all badges with per-badge earn stats."""
    registered_evaluators = set(list_registered_evaluators())

    badges = (
        db.query(Badge)
        .order_by(Badge.category, Badge.rarity, Badge.id)
        .all()
    )

    result = []
    for b in badges:
        earn_count = (
            db.query(UserBadge)
            .filter(UserBadge.badge_id == b.id)
            .count()
        )

        evaluator_config = json.loads(b.evaluator_config) if b.evaluator_config else {}
        evaluator_valid = b.evaluator_class in registered_evaluators

        result.append({
            "id": b.id,
            "title": b.title,
            "description": b.description,
            "category": b.category,
            "category_display": CATEGORY_DISPLAY.get(b.category, b.category),
            "rarity": b.rarity,
            "points": b.points,
            "is_active": b.is_active,
            "is_secret": b.is_secret,
            "icon_url": b.icon_url,
            "evaluator_class": b.evaluator_class,
            "evaluator_config": evaluator_config,
            "evaluator_valid": evaluator_valid,
            "earn_count": earn_count,
        })

    return result


@router.get("/", response_class=HTMLResponse)
async def badges_list(request: Request):
    """Badge viewer — browse all badge definitions with earn stats"""
    db = SessionLocal()
    try:
        badges = _badge_list_with_stats(db)

        total = len(badges)
        active = sum(1 for b in badges if b["is_active"])
        secret = sum(1 for b in badges if b["is_secret"])
        earned_any = sum(1 for b in badges if b["earn_count"] > 0)
        invalid_evaluators = sum(1 for b in badges if not b["evaluator_valid"])

        rarity_counts = {}
        for b in badges:
            r = b["rarity"]
            if r not in rarity_counts:
                rarity_counts[r] = {"defined": 0, "earned": 0}
            rarity_counts[r]["defined"] += 1
            if b["earn_count"] > 0:
                rarity_counts[r]["earned"] += 1

        rarity_summary = [
            {"rarity": r, **rarity_counts[r]}
            for r in sorted(rarity_counts, key=lambda x: RARITY_ORDER.get(x, 99))
        ]

        categories = sorted(set(b["category"] for b in badges))

        data = {
            "badges": badges,
            "categories": categories,
            "rarity_summary": rarity_summary,
            "summary": {
                "total": total,
                "active": active,
                "inactive": total - active,
                "secret": secret,
                "earned_any": earned_any,
                "unearned": total - earned_any,
                "invalid_evaluators": invalid_evaluators,
            },
        }
    finally:
        db.close()

    return template_response(request, "pages/badges.html", data)


@router.post("/api/toggle")
async def toggle_badge(badge_id: str = Query(...)):
    """Toggle is_active for a badge (runtime ops, overwritten on restart)."""
    db = SessionLocal()
    try:
        badge = db.query(Badge).filter(Badge.id == badge_id).first()
        if not badge:
            raise HTTPException(status_code=404, detail="Badge not found")
        badge.is_active = not badge.is_active
        db.commit()
        return {"id": badge.id, "is_active": badge.is_active}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
