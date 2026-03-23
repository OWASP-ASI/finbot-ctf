"""CC Challenges — read-only viewer + ops tool for challenge definitions"""

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from finbot.core.data.database import SessionLocal
from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.core.templates import TemplateResponse
from finbot.ctf.detectors.registry import list_registered_detectors

template_response = TemplateResponse("finbot/apps/cc/templates")

router = APIRouter(prefix="/challenges")


def _challenge_list_with_stats(db) -> list[dict]:
    """Get all challenges with per-challenge completion stats."""
    registered_detectors = set(list_registered_detectors())

    challenges = (
        db.query(Challenge)
        .order_by(Challenge.order_index, Challenge.category, Challenge.id)
        .all()
    )
    result = []
    for c in challenges:
        progress_rows = (
            db.query(UserChallengeProgress)
            .filter(UserChallengeProgress.challenge_id == c.id)
            .all()
        )

        completions = sum(1 for p in progress_rows if p.status == "completed")
        players = len(set(p.user_id for p in progress_rows))
        total_attempts = sum(p.attempts for p in progress_rows)
        hints_used = sum(p.hints_used for p in progress_rows)

        completed_rows = [p for p in progress_rows if p.status == "completed" and p.completion_time_seconds]
        avg_solve = (
            int(sum(p.completion_time_seconds for p in completed_rows) / len(completed_rows))
            if completed_rows else None
        )

        prerequisites = json.loads(c.prerequisites) if c.prerequisites else []
        hints = json.loads(c.hints) if c.hints else []
        labels = json.loads(c.labels) if c.labels else {}

        detector_valid = c.detector_class in registered_detectors

        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "subcategory": c.subcategory,
            "difficulty": c.difficulty,
            "points": c.points,
            "is_active": c.is_active,
            "detector_class": c.detector_class,
            "detector_valid": detector_valid,
            "prerequisites": prerequisites,
            "hints_count": len(hints),
            "labels": labels,
            "completions": completions,
            "players": players,
            "total_attempts": total_attempts,
            "hints_used": hints_used,
            "avg_solve_seconds": avg_solve,
        })

    return result


FRAMEWORK_DISPLAY = {
    "owasp_llm": "OWASP LLM Top 10",
    "owasp_agentic": "OWASP Agentic Security",
    "mitre_atlas": "MITRE ATLAS",
    "cwe": "CWE",
}

FRAMEWORK_ORDER = ["owasp_llm", "owasp_agentic", "mitre_atlas", "cwe"]


def _build_coverage_matrix(challenges: list[dict]) -> list[dict]:
    """Build a per-framework coverage list: each label + which challenges cover it."""
    framework_labels: dict[str, dict[str, list[str]]] = {}

    for c in challenges:
        if not c["labels"]:
            continue
        for framework, values in c["labels"].items():
            if framework not in framework_labels:
                framework_labels[framework] = {}
            for label in values:
                if label not in framework_labels[framework]:
                    framework_labels[framework][label] = []
                framework_labels[framework][label].append(c["title"])

    result = []
    for key in FRAMEWORK_ORDER:
        if key not in framework_labels:
            continue
        labels = sorted(framework_labels[key].keys())
        result.append({
            "key": key,
            "name": FRAMEWORK_DISPLAY.get(key, key),
            "labels": [
                {"id": label, "challenges": framework_labels[key][label]}
                for label in labels
            ],
        })
    return result


@router.get("/", response_class=HTMLResponse)
async def challenges_list(request: Request):
    """Challenge viewer — browse all challenge definitions with stats"""
    db = SessionLocal()
    try:
        challenges = _challenge_list_with_stats(db)

        categories = sorted(set(c["category"] for c in challenges))
        difficulties = ["beginner", "intermediate", "advanced", "expert"]

        total = len(challenges)
        active = sum(1 for c in challenges if c["is_active"])
        solved = sum(1 for c in challenges if c["completions"] > 0)
        invalid_detectors = sum(1 for c in challenges if not c["detector_valid"])

        coverage = _build_coverage_matrix(challenges)

        data = {
            "challenges": challenges,
            "categories": categories,
            "difficulties": difficulties,
            "coverage": coverage,
            "summary": {
                "total": total,
                "active": active,
                "inactive": total - active,
                "solved": solved,
                "unsolved": total - solved,
                "invalid_detectors": invalid_detectors,
            },
        }
    finally:
        db.close()

    return template_response(request, "pages/challenges.html", data)


@router.post("/api/toggle")
async def toggle_challenge(challenge_id: str = Query(...)):
    """Toggle is_active for a challenge (runtime ops, overwritten on restart)."""
    db = SessionLocal()
    try:
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        challenge.is_active = not challenge.is_active
        db.commit()
        return {"id": challenge.id, "is_active": challenge.is_active}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
