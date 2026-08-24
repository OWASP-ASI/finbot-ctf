"""Challenge Completion Service"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.core.utils import to_utc_iso
from finbot.ctf.detectors.registry import create_detector
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.processor.scoring import ScoringResult, apply_modifiers

logger = logging.getLogger(__name__)


class ChallengeService:
    """Handles challenge detection and progress tracking"""

    async def check_event_for_challenges(
        self, event: dict[str, Any], db: Session
    ) -> list[tuple[str, DetectionResult]]:
        """Check if an event completes any challenges.
        Returns list of (challenge_id, result) tuples for completed challenges.
        """
        event_type = event.get("event_type", "")
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return []

        completed = []
        challenges = db.query(Challenge).filter(Challenge.is_active).all()
        for challenge in challenges:
            config = (
                json.loads(challenge.detector_config)
                if challenge.detector_config
                else None
            )
            detector = create_detector(challenge.detector_class, challenge.id, config)
            if not detector:
                continue
            if not detector.matches_event_type(event_type):
                continue
            progress = self._get_or_create_progress(
                db, namespace, user_id, challenge.id
            )
            if progress.status == "completed":
                continue

            prerequisites = (
                json.loads(challenge.prerequisites) if challenge.prerequisites else []
            )
            if not self._check_prerequisites(db, namespace, user_id, prerequisites):
                logger.debug(
                    "Challenge %s prerequisites not met for user %s",
                    challenge.id,
                    user_id,
                )
                continue

            # Run detection
            try:
                result: DetectionResult = await detector.check_event(event, db)

                # Only count meaningful attempts: the detector must have
                # actually engaged (evidence populated or detected). Events
                # that don't match the detector's tool/agent/channel filters
                # are not real attempts.
                is_relevant = result.detected or bool(result.evidence)

                workflow_id = event.get("workflow_id")
                is_new_attempt = bool(
                    is_relevant
                    and workflow_id
                    and workflow_id != progress.last_attempt_workflow_id
                )
                if is_new_attempt:
                    progress.attempts += 1
                    progress.last_attempt_workflow_id = workflow_id
                    if progress.first_attempt_at is None:
                        progress.first_attempt_at = datetime.now(UTC)
                    if not result.detected:
                        progress.failed_attempts += 1
                    progress.status = (
                        "in_progress"
                        if progress.status == "available"
                        else progress.status
                    )

                if is_relevant:
                    progress.last_attempt_result = json.dumps({
                        "detected": result.detected,
                        "message": result.message,
                        "confidence": result.confidence,
                        "evidence": result.evidence,
                        "event_type": event.get("event_type"),
                        "timestamp": to_utc_iso(result.timestamp),
                    })

                # Commit attempt tracking to release the SQLite write lock
                # before the potentially slow scoring LLM call.
                db.commit()

                if result.detected:
                    scoring_result = await self._apply_scoring_modifiers(
                        challenge, event, result
                    )
                    self._mark_completed(
                        db, progress, event, result, scoring_result
                    )
                    db.commit()
                    completed.append((challenge.id, result))
                    logger.info(
                        "Challenge completed: %s for user %s (confidence: %.2f, modifier: %.2f)",
                        challenge.id,
                        user_id,
                        result.confidence,
                        scoring_result.modifier,
                    )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error checking challenge %s: %s", challenge.id, e)
                db.rollback()

        return completed

    def _get_or_create_progress(
        self, db: Session, namespace: str, user_id: str, challenge_id: str
    ) -> UserChallengeProgress:
        """Get or create user progress record"""
        progress = (
            db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == namespace,
                UserChallengeProgress.user_id == user_id,
                UserChallengeProgress.challenge_id == challenge_id,
            )
            .first()
        )

        if not progress:
            progress = UserChallengeProgress(
                namespace=namespace,
                user_id=user_id,
                challenge_id=challenge_id,
                status="available",
            )
            db.add(progress)
            db.flush()

        return progress

    def _check_prerequisites(
        self,
        db: Session,
        namespace: str,
        user_id: str,
        prerequisites: list[str],
    ) -> bool:
        """Return True if all prerequisite challenges are completed for this user."""
        if not prerequisites:
            return True
        for prereq_id in prerequisites:
            progress = (
                db.query(UserChallengeProgress)
                .filter(
                    UserChallengeProgress.namespace == namespace,
                    UserChallengeProgress.user_id == user_id,
                    UserChallengeProgress.challenge_id == prereq_id,
                    UserChallengeProgress.status == "completed",
                )
                .first()
            )
            if not progress:
                return False
        return True

    async def _apply_scoring_modifiers(
        self,
        challenge: Challenge,
        event: dict[str, Any],
        result: DetectionResult | None = None,
    ) -> ScoringResult:
        """Load and apply scoring modifiers for a challenge.

        The detector's own result is passed through to the modifiers under
        `detection_evidence` / `detection_confidence` so a modifier can scale
        points by how well the player actually did -- see the `detection_score`
        modifier. Copied rather than mutated so the caller's event is untouched.
        """
        if not challenge.scoring:
            return ScoringResult()

        scoring_config = json.loads(challenge.scoring)
        modifiers = scoring_config.get("modifiers", [])
        if not modifiers:
            return ScoringResult()

        modifier_event = dict(event)
        if result is not None:
            modifier_event["detection_evidence"] = result.evidence
            modifier_event["detection_confidence"] = result.confidence

        return await apply_modifiers(modifiers, modifier_event)

    def _mark_completed(
        self,
        db: Session,
        progress: UserChallengeProgress,
        event: dict[str, Any],
        result: DetectionResult,
        scoring_result: ScoringResult | None = None,
    ):
        """Mark challenge as completed"""
        now = datetime.now(UTC)

        progress.status = "completed"
        progress.successful_attempts += 1
        progress.completed_at = now

        if scoring_result:
            progress.points_modifier = scoring_result.modifier

        if progress.first_attempt_at:
            first_attempt = progress.first_attempt_at
            if first_attempt.tzinfo is None:
                first_attempt = first_attempt.replace(tzinfo=UTC)
            progress.completion_time_seconds = int(
                (now - first_attempt).total_seconds()
            )

        evidence = {
            "result_message": result.message,
            "confidence": result.confidence,
            "evidence": result.evidence,
            "event_type": event.get("event_type"),
            "timestamp": to_utc_iso(result.timestamp),
        }
        if scoring_result and scoring_result.details:
            evidence["scoring"] = {
                "modifier": scoring_result.modifier,
                "details": scoring_result.details,
            }

        progress.completion_evidence = json.dumps(evidence)
        progress.completion_workflow_id = event.get("workflow_id")
