"""Invoice data tools"""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository

logger = logging.getLogger(__name__)


async def get_invoice_details(
    invoice_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get the details of the invoice

    Args:
        invoice_id: The ID of the invoice to retrieve
        session_context: The session context

    Returns:
        Dictionary containing invoice details
    """
    logger.info("Getting invoice details for invoice_id: %s", invoice_id)
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        return invoice.to_dict()


async def update_invoice_status(
    invoice_id: int, status: str, agent_notes: str, session_context: SessionContext
) -> dict[str, Any]:
    """Update the status of the invoice

    Args:
        invoice_id: The ID of the invoice to update
        status: The new status of the invoice
        agent_notes: The reason behind the update
        session_context: The session context
    """
    logger.info(
        "Updating invoice status for invoice_id: %s to status: %s. Agent notes: %s",
        invoice_id,
        status,
        agent_notes,
    )
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")

        previous_state = {
            "status": invoice.status,
        }
        existing_notes = invoice.agent_notes or ""
        new_notes = f"{existing_notes}\n\n{agent_notes}"
        invoice = invoice_repo.update_invoice(
            invoice_id, status=status, agent_notes=new_notes
        )
        if not invoice:
            raise ValueError("Invoice not found")

        result = invoice.to_dict()
        result["_previous_state"] = previous_state

        return result


async def update_invoice_agent_notes(
    invoice_id: int,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update the agent notes of the invoice"""
    logger.info(
        "Updating invoice agent notes for invoice_id: %s. Agent notes: %s",
        invoice_id,
        agent_notes,
    )
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
                if agent_notes is None:
            return invoice.to_dict()

        existing_notes = invoice.agent_notes or ""
        new_notes = f"{existing_notes}\n\n{agent_notes}"
        invoice = invoice_repo.update_invoice(
            invoice_id,
            agent_notes=new_notes,
        )
        if not invoice:
            raise ValueError("Invoice not found")
        return invoice.to_dict()
