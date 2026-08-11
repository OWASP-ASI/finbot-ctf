"""Enrich guardrail hook payloads with read-only context for defender webhooks."""

from __future__ import annotations

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.models import Invoice

logger = logging.getLogger(__name__)

_INVOICE_AMOUNT_TOOLS = frozenset(
    {
        "update_invoice_status",
        "finstripe__create_transfer",
    }
)


def enrich_tool_arguments_for_hook(
    tool_name: str | None,
    tool_arguments: dict[str, Any] | None,
    session_context: SessionContext,
) -> dict[str, Any] | None:
    """Add defender context to tool_arguments before the webhook POST.

    For invoice-scoped tools, FinBot attaches ``invoice_amount`` from the
    database so external guardrails can enforce dollar thresholds without a
    separate invoice lookup API.
    """
    if not tool_arguments or tool_name not in _INVOICE_AMOUNT_TOOLS:
        return tool_arguments

    invoice_id = tool_arguments.get("invoice_id")
    if invoice_id is None:
        return tool_arguments

    try:
        invoice_id_int = int(invoice_id)
    except (TypeError, ValueError):
        return tool_arguments

    try:
        with db_session() as db:
            invoice = (
                db.query(Invoice)
                .filter(
                    Invoice.id == invoice_id_int,
                    Invoice.namespace == session_context.namespace,
                )
                .first()
            )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to enrich invoice_amount for guardrail hook",
            exc_info=True,
        )
        return tool_arguments

    if not invoice:
        return tool_arguments

    enriched = dict(tool_arguments)
    enriched["invoice_amount"] = float(invoice.amount)
    return enriched
