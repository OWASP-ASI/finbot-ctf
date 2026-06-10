"""Payment data tools"""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository, VendorRepository

logger = logging.getLogger(__name__)


async def get_invoice_for_payment(
    invoice_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get invoice details relevant for payment processing

    Args:
        invoice_id: The ID of the invoice to retrieve
        session_context: The session context

    Returns:
        Dictionary containing invoice details with vendor info for payment
    """
    logger.info("Getting invoice for payment, invoice_id: %s", invoice_id)
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")

        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(invoice.vendor_id)

        result = invoice.to_dict()
        if vendor:
            result["vendor_company_name"] = vendor.company_name
            result["vendor_status"] = vendor.status
            result["vendor_trust_level"] = vendor.trust_level
            result["vendor_bank_name"] = vendor.bank_name
            result["vendor_bank_account_number"] = vendor.bank_account_number
            result["vendor_bank_routing_number"] = vendor.bank_routing_number
            result["vendor_bank_account_holder_name"] = vendor.bank_account_holder_name
        return result


async def process_payment(
    invoice_id: int,
    payment_method: str,
    payment_reference: str,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Process payment for an approved invoice (transition to 'paid')

    Args:
        invoice_id: The ID of the invoice to pay
        payment_method: Payment method used (e.g., 'bank_transfer', 'wire', 'ach')
        payment_reference: External payment reference number
        agent_notes: Notes about the payment processing
        session_context: The session context

    Returns:
        Dictionary containing payment result
    """
    if not payment_method or not isinstance(payment_method, str) or not payment_method.strip():
        raise ValueError("payment_method is required and cannot be empty")
    if payment_reference is None:
        raise ValueError("payment_reference is required")

    logger.info(
        "Processing payment for invoice_id: %s, method: %s, ref: %s",
        invoice_id,
        payment_method,
        payment_reference,
    )
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")

        previous_state = {
            "status": invoice.status,
        }

        if invoice.status not in ("approved",):
            raise ValueError(
                f"Invoice status is '{invoice.status}', only 'approved' invoices can be paid"
            )

        existing_notes = invoice.agent_notes or ""
        payment_note = (
            f"Payment processed via {payment_method} (ref: {payment_reference}). "
            f"{agent_notes}"
        )
        new_notes = f"{existing_notes}\n\n{payment_note}"

        invoice = invoice_repo.update_invoice(
            invoice_id, status="paid", agent_notes=new_notes
        )
        if not invoice:
            raise ValueError("Failed to update invoice")

        result = invoice.to_dict()
        result["_previous_state"] = previous_state
        result["payment_method"] = payment_method
        result["payment_reference"] = payment_reference
        return result


async def get_vendor_payment_summary(
    vendor_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get payment summary for a vendor (all invoices grouped by status)

    Args:
        vendor_id: The ID of the vendor
        session_context: The session context

    Returns:
        Dictionary containing payment summary
    """
    logger.info("Getting payment summary for vendor_id: %s", vendor_id)
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        invoice_repo = InvoiceRepository(db, session_context)
        invoices = invoice_repo.list_invoices_for_specific_vendor(vendor_id)

        summary = {
            "vendor_id": vendor_id,
            "company_name": vendor.company_name,
            "vendor_status": vendor.status,
            "vendor_trust_level": vendor.trust_level,
            "total_invoices": len(invoices),
            "total_amount": 0.0,
            "by_status": {},
            "invoices": [],
        }

        for invoice in invoices:
            amount = float(invoice.amount) if invoice.amount else 0.0
            summary["total_amount"] += amount
            status = invoice.status or "unknown"
            if status not in summary["by_status"]:
                summary["by_status"][status] = {"count": 0, "amount": 0.0}
            summary["by_status"][status]["count"] += 1
            summary["by_status"][status]["amount"] += amount
            summary["invoices"].append(
                {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "amount": amount,
                    "status": invoice.status,
                    "due_date": invoice.due_date.isoformat().replace("+00:00", "Z")
                    if invoice.due_date
                    else None,
                }
            )

        return summary


async def update_payment_agent_notes(
    invoice_id: int,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update agent notes on an invoice for payment processing context

    Args:
        invoice_id: The ID of the invoice
        agent_notes: Notes to append
        session_context: The session context

    Returns:
        Dictionary containing updated invoice
    """
    if agent_notes is None:
        raise ValueError("agent_notes is required and cannot be None")

    logger.info(
        "Updating payment agent notes for invoice_id: %s. Agent notes: %s",
        invoice_id,
        agent_notes,
    )
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoice = invoice_repo.get_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        existing_notes = invoice.agent_notes or ""
        new_notes = f"{existing_notes}\n\n[Payments Agent] {agent_notes}"
        invoice = invoice_repo.update_invoice(
            invoice_id,
            agent_notes=new_notes,
        )
        if not invoice:
            raise ValueError("Invoice not found")
        return invoice.to_dict()
