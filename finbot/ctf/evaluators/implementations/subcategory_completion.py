"""Subcategory Completion Evaluator"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("SubcategoryCompletionEvaluator")
class SubcategoryCompletionEvaluator(BaseEvaluator):
    """Awards badges based on completing challenges with a specific attack subcategory.

    Configuration:
        min_count: Minimum number of completed challenges required
        challenge_subcategory: Required subcategory (e.g., tool_poisoning, indirect_injection)
    """

    def _validate_config(self) -> None:
        if "min_count" not in self.config:
            raise ValueError("min_count is required")
        if "challenge_subcategory" not in self.config:
            raise ValueError("challenge_subcategory is required")

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.*.task_completion"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return DetectionResult(detected=False, message="Missing namespace or user_id")

        min_count = self.config["min_count"]
        subcategory = self.config["challenge_subcategory"]

        count = self._count_completed(db, namespace, user_id, subcategory)

        if count >= min_count:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=(
                    f"User completed {count} {subcategory} challenges " f"(required: {min_count})"
                ),
                evidence={
                    "completed_count": count,
                    "required_count": min_count,
                    "subcategory": subcategory,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_count if min_count > 0 else 0,
            message=f"User completed {count}/{min_count} {subcategory} challenges",
            evidence={
                "completed_count": count,
                "required_count": min_count,
                "subcategory": subcategory,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        min_count = self.config["min_count"]
        subcategory = self.config["challenge_subcategory"]
        count = self._count_completed(db, namespace, user_id, subcategory)

        return {
            "current": count,
            "target": min_count,
            "percentage": min(100, int((count / min_count) * 100)) if min_count > 0 else 100,
            "subcategory": subcategory,
        }

    def _count_completed(
        self,
        db: Session,
        namespace: str,
        user_id: str,
        subcategory: str,
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
            .filter(Challenge.subcategory == subcategory)
            .scalar()
            or 0
        )
