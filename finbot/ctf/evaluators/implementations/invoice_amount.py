"""Invoice Amount Evaluator"""

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


@register_evaluator("InvoiceAmountEvaluator")
class InvoiceAmountEvaluator(BaseEvaluator):
    """Awards badges based on cumulative invoice amount.

    Configuration:
        min_amount: Minimum total amount required to earn the badge
        invoice_status: Optional status filter (default: counts all statuses)
    """

    def _validate_config(self) -> None:
        if "min_amount" not in self.config:
            raise ValueError("min_amount is required")

        invoice_status = self.config.get("invoice_status")
        if invoice_status is not None and invoice_status not in VALID_STATUSES:
            raise ValueError(f"Invalid invoice status: {invoice_status}")

    def get_relevant_event_types(self) -> list[str]:
        return [
            "agent.invoice_agent.task_completion",
            "agent.payments_agent.task_completion",
        ]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if user has reached the target invoice amount."""
        namespace = event.get("namespace")
        if not namespace:
            return DetectionResult(detected=False, message="Namespace not found in event")

        min_amount = self.config.get("min_amount", 0)
        invoice_status = self.config.get("invoice_status")

        total = self._sum_invoices(db, namespace, invoice_status)

        if total >= min_amount:
            return DetectionResult(
                detected=True,
                confidence=1.0,
                message=f"Total invoice amount ${total:,.2f} (required: ${min_amount:,.2f})",
                evidence={
                    "total_amount": total,
                    "required_amount": min_amount,
                    "status_filter": invoice_status,
                },
            )

        return DetectionResult(
            detected=False,
            confidence=total / min_amount if min_amount > 0 else 0,
            message=f"Total invoice amount ${total:,.2f} / ${min_amount:,.2f}",
            evidence={
                "total_amount": total,
                "required_amount": min_amount,
            },
        )

    def get_progress(self, namespace: str, user_id: str, db: Session) -> dict[str, Any]:
        """Get progress toward badge"""
        min_amount = self.config.get("min_amount", 0)
        invoice_status = self.config.get("invoice_status")

        total = self._sum_invoices(db, namespace, invoice_status)

        return {
            "current": total,
            "target": min_amount,
            "percentage": min(100, int((total / min_amount) * 100)) if min_amount > 0 else 100,
            "status_filter": invoice_status,
        }

    def _sum_invoices(self, db: Session, namespace: str, invoice_status: str | None) -> float:
        # pylint: disable=not-callable
        query = db.query(func.coalesce(func.sum(Invoice.amount), 0)).filter(
            Invoice.namespace == namespace
        )
        if invoice_status:
            query = query.filter(Invoice.status == invoice_status)
        return float(query.scalar())
