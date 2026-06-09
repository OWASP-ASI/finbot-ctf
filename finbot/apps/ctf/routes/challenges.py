"""CTF Challenges API Routes"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_authenticated_session_context, get_session_context
from finbot.core.utils import to_utc_iso
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    ChallengeRepository,
    UserChallengeProgressRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["challenges"])


class ChallengeListItem(BaseModel):
    """Challenge list item model"""

    id: str
    title: str
    category: str
    subcategory: str | None
    difficulty: str
    points: int
    image_url: str | None
    status: str
    is_active: bool


class ChallengeDetail(BaseModel):
    """Challenge detail model"""

    id: str
    title: str
    description: str
    category: str
    subcategory: str | None
    difficulty: str
    points: int
    image_url: str | None
    hints: list[dict]
    labels: dict
    prerequisites: list[str]
    resources: list[dict]
    status: str
    attempts: int
    hints_used: int
    hints_cost: int
    points_modifier: float = 1.0
    effective_points: int | None = None
    completed_at: str | None
    completion_evidence: dict | None = None
    last_attempt_result: dict | None = None


class CheckResult(BaseModel):
    """Check result model"""

    status: str
    detected: bool
    message: str | None
    confidence: float


class HintResponse(BaseModel):
    """Hint response model"""

    hint_index: int
    hint_text: str
    points_deducted: int
    total_hints_cost: int


@router.get("/challenges", response_model=list[ChallengeListItem])
def list_challenges(
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
    status: str | None = Query(None),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """List all challenges with optional filters"""
    challenge_repo = ChallengeRepository(db)
    challenges = challenge_repo.list_challenges(
        category=category, difficulty=difficulty
    )

    # Get user progress
    progress_map = {}
    if session_context:
        progress_repo = UserChallengeProgressRepository(db, session_context)
        progress_map = progress_repo.get_progress_map()

    result = []
    for c in challenges:
        user_status = progress_map.get(c.id, "available")

        if status and user_status != status:
            continue

        result.append(
            ChallengeListItem(
                id=c.id,
                title=c.title,
                category=c.category,
                subcategory=c.subcategory,
                difficulty=c.difficulty,
                points=c.points,
                image_url=c.image_url,
                status=user_status,
                is_active=c.is_active,
            )
        )

    return result


@router.get("/challenges/{challenge_id}", response_model=ChallengeDetail)
def get_challenge(
    challenge_id: str,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get challenge details with user progress"""
    challenge_repo = ChallengeRepository(db)
    challenge = challenge_repo.get_challenge(challenge_id)

    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    # Get user progress
    progress = None
    if session_context:
        progress_repo = UserChallengeProgressRepository(db, session_context)
        progress = progress_repo.get_progress(challenge_id)

    # Parse JSON fields
    hints = json.loads(challenge.hints) if challenge.hints else []
    labels = json.loads(challenge.labels) if challenge.labels else {}
    prerequisites = (
        json.loads(challenge.prerequisites) if challenge.prerequisites else []
    )
    resources = json.loads(challenge.resources) if challenge.resources else []

    # Mask hints user hasn't unlocked
    hints_used = progress.hints_used if progress else 0
    masked_hints = []
    for i, hint in enumerate(hints):
        if i < hints_used:
            masked_hints.append(hint)
        else:
            masked_hints.append({"cost": hint["cost"], "text": "[locked]"})

    # Parse completion evidence for completed challenges
    completion_evidence = None
    if progress and progress.status == "completed" and progress.completion_evidence:
        try:
            completion_evidence = json.loads(progress.completion_evidence)
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse last attempt result for in-progress challenges
    last_attempt_result = None
    if progress and progress.last_attempt_result:
        try:
            last_attempt_result = json.loads(progress.last_attempt_result)
        except (json.JSONDecodeError, TypeError):
            pass

    modifier = (
        progress.points_modifier
        if progress and progress.points_modifier is not None
        else 1.0
    )

    return ChallengeDetail(
        id=challenge.id,
        title=challenge.title,
        description=challenge.description,
        category=challenge.category,
        subcategory=challenge.subcategory,
        difficulty=challenge.difficulty,
        points=challenge.points,
        image_url=challenge.image_url,
        hints=masked_hints,
        labels=labels,
        prerequisites=prerequisites,
        resources=resources,
        status=progress.status if progress else "available",
        attempts=progress.attempts if progress else 0,
        hints_used=hints_used,
        hints_cost=progress.hints_cost if progress else 0,
        points_modifier=modifier,
        effective_points=int(challenge.points * modifier),
        completed_at=to_utc_iso(progress.completed_at)
        if progress and progress.completed_at
        else None,
        completion_evidence=completion_evidence,
        last_attempt_result=last_attempt_result,
    )


@router.post("/challenges/{challenge_id}/check", response_model=CheckResult)
def check_challenge(
    challenge_id: str,
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """On-demand challenge progress check.

    Returns current progress status from the database. Detection happens
    in real-time through the event pipeline — this endpoint just reflects
    what has already been detected.

    Requires a persistent (email-bound) session — temporary sessions receive
    HTTP 401 via get_authenticated_session_context.
    """

    challenge_repo = ChallengeRepository(db)
    challenge = challenge_repo.get_challenge(challenge_id)

    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    progress_repo = UserChallengeProgressRepository(db, session_context)
    progress = progress_repo.get_progress(challenge_id)

    if progress and progress.status == "completed":
        return CheckResult(
            status="completed",
            detected=True,
            message="Challenge already completed",
            confidence=1.0,
        )

    # Record the check attempt
    progress_repo.record_attempt(challenge_id)

    if progress and progress.status == "in_progress":
        return CheckResult(
            status="in_progress",
            detected=False,
            message="Challenge in progress — keep interacting with the AI agent in the Vendor Portal. Detection happens automatically.",
            confidence=0.0,
        )

    return CheckResult(
        status="available",
        detected=False,
        message="No progress yet. Head to the Vendor Portal and interact with the AI agent to attempt this challenge.",
        confidence=0.0,
    )


@router.post("/challenges/{challenge_id}/hint", response_model=HintResponse)
def use_hint(
    challenge_id: str,
    session_context: SessionContext = Depends(get_authenticated_session_context),
    db: Session = Depends(get_db),
):
    """Use the next available hint.

    Requires a persistent (email-bound) session — temporary sessions receive
    HTTP 401 via get_authenticated_session_context.
    """

    challenge_repo = ChallengeRepository(db)
    challenge = challenge_repo.get_challenge(challenge_id)

    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    hints = json.loads(challenge.hints) if challenge.hints else []
    if not hints:
        raise HTTPException(status_code=400, detail="No hints available")

    progress_repo = UserChallengeProgressRepository(db, session_context)
    progress = progress_repo.get_progress(challenge_id)

    current_hints_used = progress.hints_used if progress else 0
    if current_hints_used >= len(hints):
        raise HTTPException(status_code=400, detail="All hints already used")

    # Get next hint
    hint = hints[current_hints_used]

    # Don't charge points if the challenge is already completed
    is_completed = progress and progress.status == "completed"
    cost = 0 if is_completed else hint["cost"]

    # Use hint
    updated_progress = progress_repo.use_hint(challenge_id, cost)

    return HintResponse(
        hint_index=current_hints_used,
        hint_text=hint["text"],
        points_deducted=cost,
        total_hints_cost=updated_progress.hints_cost,
    )
