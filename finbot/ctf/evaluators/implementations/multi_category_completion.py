"""Multi-Category Completion Evaluator"""

import logging
from typing import Any

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("MultiCategoryCompletionEvaluator")
class MultiCategoryCompletionEvaluator(BaseEvaluator):
    """Awards badges when a user has completed challenges across N distinct categories.

    Configuration:
        min_categories: Minimum number of distinct challenge categories with completions
    """

    def _validate_config(self) -> None:
        if "min_categories" not in self.config:
            raise ValueError("min_categories is required")

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.*.task_completion"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return DetectionResult(detected=False, message="Missing namespace or user_id")

        min_categories = self.config["min_categories"]
        count = self._count_categories(db, namespace, user_id)

        if count >= min_categories:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=(
                    f"User completed challenges across {count} categories "
                    f"(required: {min_categories})"
                ),
                evidence={
                    "category_count": count,
                    "required_categories": min_categories,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_categories if min_categories > 0 else 0,
            message=(f"User completed challenges across {count}/{min_categories} categories"),
            evidence={
                "category_count": count,
                "required_categories": min_categories,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        min_categories = self.config["min_categories"]
        count = self._count_categories(db, namespace, user_id)

        return {
            "current": count,
            "target": min_categories,
            "percentage": (
                min(100, int((count / min_categories) * 100)) if min_categories > 0 else 100
            ),
        }

    def _count_categories(self, db: Session, namespace: str, user_id: str) -> int:
        # pylint: disable=not-callable
        return (
            db.query(func.count(distinct(Challenge.category)))
            .join(
                UserChallengeProgress,
                UserChallengeProgress.challenge_id == Challenge.id,
            )
            .filter(
                UserChallengeProgress.namespace == namespace,
                UserChallengeProgress.user_id == user_id,
                UserChallengeProgress.status == "completed",
            )
            .scalar()
            or 0
        )
