"""Vendor Count Evaluator"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.data.models import Vendor
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("VendorCountEvaluator")
class VendorCountEvaluator(BaseEvaluator):
    """Awards badges based on vendor count.

    Configuration:
        min_count: Minimum number of vendors required to earn the badge
        vendor_status: Optional status of vendors to count (default: active)
    """

    def _validate_config(self) -> None:
        """Validate evaluator configuration"""
        if "min_count" not in self.config:
            raise ValueError("min_count is required")

        valid_statuses = ["pending", "active", "inactive", None]
        vendor_status = self.config.get("vendor_status")
        if vendor_status is not None and vendor_status not in valid_statuses:
            raise ValueError(f"Invalid vendor status: {vendor_status}")

    def get_relevant_event_types(self) -> list[str]:
        """Trigger on vendor creation events"""
        return [
            "agent.onboarding_agent.task_completion",
        ]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if user has created enough vendors."""
        namespace = event.get("namespace")
        if not namespace:
            return DetectionResult(detected=False, message="Namespace not found in event")

        min_count = self.config.get("min_count", 1)
        vendor_status = self.config.get("vendor_status")

        # Query vendor count
        # pylint: disable=not-callable
        query = db.query(func.count(Vendor.id)).filter(Vendor.namespace == namespace)

        if vendor_status:
            query = query.filter(Vendor.status == vendor_status)

        count = query.scalar() or 0

        if count >= min_count:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"User has {count} vendors (required: {min_count})",
                evidence={
                    "vendor_count": count,
                    "required_count": min_count,
                    "status_filter": vendor_status,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_count if min_count > 0 else 0,
            message=f"User has {count}/{min_count} vendors",
            evidence={
                "vendor_count": count,
                "required_count": min_count,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        """Get progress toward badge"""
        min_count = self.config.get("min_count", 1)
        vendor_status = self.config.get("vendor_status")

        # pylint: disable=not-callable
        query = db.query(func.count(Vendor.id)).filter(Vendor.namespace == namespace)

        if vendor_status:
            query = query.filter(Vendor.status == vendor_status)

        count = query.scalar() or 0

        return {
            "current": count,
            "target": min_count,
            "percentage": min(100, int((count / min_count) * 100)) if min_count > 0 else 100,
            "status_filter": vendor_status,
        }
