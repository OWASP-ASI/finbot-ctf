"""Point Threshold Evaluator"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import UserChallengeProgress
from finbot.core.data.repositories import ChallengeRepository
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("PointThresholdEvaluator")
class PointThresholdEvaluator(BaseEvaluator):
    """Awards badges when a user's total effective CTF score reaches a threshold.

    Uses effective points (base * modifier) to account for scoring penalties.

    Configuration:
        min_points: Minimum total effective points required
    """

    def _validate_config(self) -> None:
        if "min_points" not in self.config:
            raise ValueError("min_points is required")

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.*.task_completion"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return DetectionResult(detected=False, message="Missing namespace or user_id")

        min_points = self.config["min_points"]
        total = self._get_effective_points(db, namespace, user_id)

        if total >= min_points:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"User earned {total} points (required: {min_points})",
                evidence={
                    "total_points": total,
                    "required_points": min_points,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=total / min_points if min_points > 0 else 0,
            message=f"User earned {total}/{min_points} points",
            evidence={
                "total_points": total,
                "required_points": min_points,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        min_points = self.config["min_points"]
        total = self._get_effective_points(db, namespace, user_id)

        return {
            "current": total,
            "target": min_points,
            "percentage": min(100, int((total / min_points) * 100)) if min_points > 0 else 100,
        }

    def _get_effective_points(self, db: Session, namespace: str, user_id: str) -> int:
        completed = (
            db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == namespace,
                UserChallengeProgress.user_id == user_id,
                UserChallengeProgress.status == "completed",
            )
            .all()
        )
        if not completed:
            return 0

        repo = ChallengeRepository(db)
        return repo.get_effective_points(completed)
