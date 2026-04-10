"""Invoice Count Evaluator"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.data.models import Invoice
from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)

VALID_STATUSES = ["submitted", "processing", "approved", "rejected", "paid"]


@register_evaluator("InvoiceCountEvaluator")
class InvoiceCountEvaluator(BaseEvaluator):
    """Awards badges based on processed invoice count.

    Configuration:
        min_count: Minimum number of invoices required to earn the badge
        invoice_status: Optional status filter (default: counts all statuses)
    """

    def _validate_config(self) -> None:
        if "min_count" not in self.config:
            raise ValueError("min_count is required")

        invoice_status = self.config.get("invoice_status")
        if invoice_status is not None and invoice_status not in VALID_STATUSES:
            raise ValueError(f"Invalid invoice status: {invoice_status}")

    def get_relevant_event_types(self) -> list[str]:
        return [
            "agent.invoice_agent.task_completion",
            "agent.payments_agent.task_completion",
        ]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if user has processed enough invoices."""
        namespace = event.get("namespace")
        if not namespace:
            return DetectionResult(
                detected=False, message="Namespace not found in event"
            )

        user_id = event.get("user_id")
        if not user_id:
            return DetectionResult(
                detected=False, message="user_id not found in event"
            )

        min_count = self.config.get("min_count", 1)
        invoice_status = self.config.get("invoice_status")

        count = self._count_invoices(db, namespace, user_id, invoice_status)

        if count >= min_count:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"User has {count} invoices (required: {min_count})",
                evidence={
                    "invoice_count": count,
                    "required_count": min_count,
                    "status_filter": invoice_status,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=count / min_count if min_count > 0 else 0,
            message=f"User has {count}/{min_count} invoices",
            evidence={
                "invoice_count": count,
                "required_count": min_count,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        """Get progress toward badge"""
        min_count = self.config.get("min_count", 1)
        invoice_status = self.config.get("invoice_status")

        count = self._count_invoices(db, namespace, user_id, invoice_status)

        return {
            "current": count,
            "target": min_count,
            "percentage": min(100, int((count / min_count) * 100))
            if min_count > 0
            else 100,
            "status_filter": invoice_status,
        }

    def _count_invoices(
        self, db: Session, namespace: str, user_id: str, invoice_status: str | None
    ) -> int:
        # pylint: disable=not-callable
        query = db.query(func.count(Invoice.id)).filter(
            Invoice.namespace == namespace,
            Invoice.created_by == user_id,
        )
        if invoice_status:
            query = query.filter(Invoice.status == invoice_status)
        return query.scalar() or 0
