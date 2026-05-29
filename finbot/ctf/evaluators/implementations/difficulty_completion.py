"""Difficulty Completion Evaluator"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)

VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced", "expert"}


@register_evaluator("DifficultyCompletionEvaluator")
class DifficultyCompletionEvaluator(BaseEvaluator):
    """Awards badges based on completing challenges at a specific difficulty level.

    Configuration:
        min_count: Minimum number of completed challenges required
        difficulty: Required difficulty level (beginner, intermediate, advanced, expert)
    """

    def _validate_config(self) -> None:
        if "min_count" not in self.config:
            raise ValueError("min_count is required")
        if "difficulty" not in self.config:
            raise ValueError("difficulty is required")
        if self.config["difficulty"] not in VALID_DIFFICULTIES:
            raise ValueError(
                f"difficulty must be one of {VALID_DIFFICULTIES}, "
                f"got '{self.config['difficulty']}'"
            )

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.*.task_completion"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return DetectionResult(detected=False, message="Missing namespace or user_id")

        min_count = self.config["min_count"]
        difficulty = self.config["difficulty"]

        count = self._count_completed(db, namespace, user_id, difficulty)

        if count >= min_count:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=(
                    f"User completed {count} {difficulty} challenges " f"(required: {min_count})"
                ),
                evidence={
                    "completed_count": count,
                    "required_count": min_count,
                    "difficulty": difficulty,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_count if min_count > 0 else 0,
            message=f"User completed {count}/{min_count} {difficulty} challenges",
            evidence={
                "completed_count": count,
                "required_count": min_count,
                "difficulty": difficulty,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        min_count = self.config["min_count"]
        difficulty = self.config["difficulty"]
        count = self._count_completed(db, namespace, user_id, difficulty)

        return {
            "current": count,
            "target": min_count,
            "percentage": min(100, int((count / min_count) * 100)) if min_count > 0 else 100,
            "difficulty": difficulty,
        }

    def _count_completed(
        self,
        db: Session,
        namespace: str,
        user_id: str,
        difficulty: str,
    ) -> int:
        # pylint: disable=not-callable
        return (
            db.query(func.count(UserChallengeProgress.id))
            .filter(
                UserChallengeProgress.namespace == namespace,
                UserChallengeProgress.user_id == user_id,
                UserChallengeProgress.status == "completed",
            )
            .join(Challenge)
            .filter(Challenge.difficulty == difficulty)
            .scalar()
            or 0
        )
