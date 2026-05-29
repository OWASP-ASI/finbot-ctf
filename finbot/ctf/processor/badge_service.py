"""Badge Awarding Service"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import Badge, UserBadge
from finbot.core.utils import to_utc_iso
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators import create_evaluator

logger = logging.getLogger(__name__)


class BadgeService:
    """Handles badge evaluation and awarding"""

    async def check_event_for_badges(
        self, event: dict[str, Any], db: Session
    ) -> list[tuple[str, DetectionResult]]:
        """
        Check if an event earns any badges.

        Returns list of (badge_id, result) tuples for earned badges.
        """
        event_type = event.get("event_type", "")
        namespace = event.get("namespace")
        user_id = event.get("user_id")

        if not namespace or not user_id:
            return []

        awarded = []
        badges = db.query(Badge).filter(Badge.is_active).all()
        for badge in badges:
            config = json.loads(badge.evaluator_config) if badge.evaluator_config else None
            evaluator = create_evaluator(badge.evaluator_class, badge.id, config)
            if evaluator is None:
                continue
            if not evaluator.matches_event_type(event_type):
                continue
            # Check if user already has this badge
            existing = (
                db.query(UserBadge)
                .filter(
                    UserBadge.namespace == namespace,
                    UserBadge.user_id == user_id,
                    UserBadge.badge_id == badge.id,
                )
                .first()
            )

            if existing:
                continue

            # Run evaluation
            try:
                result: DetectionResult = await evaluator.check_event(event, db)

                if result.detected:
                    self._award_badge(db, namespace, user_id, badge, event, result)
                    awarded.append((badge.id, result))
                    logger.info("Badge awarded: %s to user %s", badge.id, user_id)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error checking badge %s: %s", badge.id, e)
                db.rollback()

        return awarded

    def _award_badge(
        self,
        db: Session,
        namespace: str,
        user_id: str,
        badge: Badge,
        event: dict[str, Any],
        result: DetectionResult,
    ):
        """Award badge to user"""
        user_badge = UserBadge(
            namespace=namespace,
            user_id=user_id,
            badge_id=badge.id,
            earned_at=datetime.now(UTC),
            earning_context=json.dumps(
                {
                    "result_message": result.message,
                    "evidence": result.evidence,
                    "event_type": event.get("event_type"),
                    "timestamp": to_utc_iso(result.timestamp),
                }
            ),
            earning_workflow_id=event.get("workflow_id"),
        )
        db.add(user_badge)
        db.commit()
