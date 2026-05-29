"""Challenge Completion Evaluator"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.data.models import Challenge, UserChallengeProgress
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("ChallengeCompletionEvaluator")
class ChallengeCompletionEvaluator(BaseEvaluator):
    """Awards badges based on completed challenge count.

    Runs after challenge detectors in the event processing pipeline,
    so newly completed challenges are already persisted by the time
    this evaluator queries the database.

    Configuration:
        min_count: Minimum number of completed challenges required
        challenge_category: Optional category filter (e.g., "recon", "policy_bypass")
    """

    def _validate_config(self) -> None:
        if "min_count" not in self.config:
            raise ValueError("min_count is required")

    def get_relevant_event_types(self) -> list[str]:
        return [
            "agent.*.task_completion",
        ]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if user has completed enough challenges."""
        namespace = event.get("namespace")
        user_id = event.get("user_id")
        if not namespace or not user_id:
            return DetectionResult(detected=False, message="Missing namespace or user_id")

        min_count = self.config.get("min_count", 1)
        category = self.config.get("challenge_category")

        count = self._count_completed(db, namespace, user_id, category)

        if count >= min_count:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"User completed {count} challenges (required: {min_count})",
                evidence={
                    "completed_count": count,
                    "required_count": min_count,
                    "category_filter": category,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_count if min_count > 0 else 0,
            message=f"User completed {count}/{min_count} challenges",
            evidence={
                "completed_count": count,
                "required_count": min_count,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        """Get progress toward badge"""
        min_count = self.config.get("min_count", 1)
        category = self.config.get("challenge_category")

        count = self._count_completed(db, namespace, user_id, category)

        return {
            "current": count,
            "target": min_count,
            "percentage": min(100, int((count / min_count) * 100)) if min_count > 0 else 100,
            "category_filter": category,
        }

    def _count_completed(
        self,
        db: Session,
        namespace: str,
        user_id: str,
        category: str | None,
    ) -> int:
        # pylint: disable=not-callable
        query = db.query(func.count(UserChallengeProgress.id)).filter(
            UserChallengeProgress.namespace == namespace,
            UserChallengeProgress.user_id == user_id,
            UserChallengeProgress.status == "completed",
        )

        if category:
            query = query.join(Challenge).filter(Challenge.category == category)

        return query.scalar() or 0
