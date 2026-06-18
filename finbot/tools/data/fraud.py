"""Fraud and compliance data tools"""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository, VendorRepository

logger = logging.getLogger(__name__)


async def get_vendor_risk_profile(
    vendor_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get comprehensive vendor risk profile for fraud assessment

    Args:
        vendor_id: The ID of the vendor
        session_context: The session context

    Returns:
        Dictionary containing vendor risk profile with invoice statistics
    """
    logger.info("Getting vendor risk profile for vendor_id: %s", vendor_id)
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        invoice_repo = InvoiceRepository(db, session_context)
        invoices = invoice_repo.list_invoices_for_specific_vendor(vendor_id)

        total_amount = 0.0
        status_counts = {}
        amounts_by_status = {}
        for invoice in invoices:
            amount = float(invoice.amount) if invoice.amount else 0.0
            total_amount += amount
            status = invoice.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            amounts_by_status[status] = amounts_by_status.get(status, 0.0) + amount

        return {
            "vendor_id": vendor.id,
            "company_name": vendor.company_name,
            "vendor_category": vendor.vendor_category,
            "industry": vendor.industry,
            "services": vendor.services,
            "status": vendor.status,
            "trust_level": vendor.trust_level,
            "risk_level": vendor.risk_level,
            "agent_notes": vendor.agent_notes,
            "created_at": vendor.created_at.isoformat().replace("+00:00", "Z"),
            "total_invoices": len(invoices),
            "total_invoice_amount": total_amount,
            "invoices_by_status": status_counts,
            "amounts_by_status": amounts_by_status,
        }


async def get_vendor_invoices(
    vendor_id: int, session_context: SessionContext
) -> list[dict[str, Any]]:
    """Get all invoices for a vendor for pattern analysis

    Args:
        vendor_id: The ID of the vendor
        session_context: The session context

    Returns:
        List of invoice dictionaries
    """
    logger.info("Getting invoices for vendor_id: %s", vendor_id)
    with db_session() as db:
        invoice_repo = InvoiceRepository(db, session_context)
        invoices = invoice_repo.list_invoices_for_specific_vendor(vendor_id)
        return [invoice.to_dict() for invoice in invoices]


async def update_vendor_risk(
    vendor_id: int,
    risk_level: str,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update vendor risk level based on fraud assessment

    Args:
        vendor_id: The ID of the vendor
        risk_level: New risk level ('low', 'medium', 'high')
        agent_notes: Fraud assessment notes
        session_context: The session context

    Returns:
        Dictionary containing updated vendor details

    Raises:
        ValueError: If risk_level is not one of the allowed values.
    """
    logger.info(
        "Updating vendor risk for vendor_id: %s to risk_level: %s. Notes: %s",
        vendor_id,
        risk_level,
        agent_notes,
    )

    # Validate risk_level against allowed values
    VALID_RISK_LEVELS = {"low", "medium", "high"}
    if risk_level not in VALID_RISK_LEVELS:
        raise ValueError(
            f"Invalid risk_level: {risk_level!r}. Must be one of {VALID_RISK_LEVELS}"
        )

    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        previous_state = {
            "risk_level": vendor.risk_level,
            "trust_level": vendor.trust_level,
            "status": vendor.status,
        }

        existing_notes = vendor.agent_notes or ""
        new_notes = f"{existing_notes}\n\n[Fraud Agent] {agent_notes}"

        vendor = vendor_repo.update_vendor(
            vendor_id,
            risk_level=risk_level,
            agent_notes=new_notes,
        )
        if not vendor:
            raise ValueError("Vendor not found")

        result = vendor.to_dict()
        result["_previous_state"] = previous_state
        return result

async def flag_invoice_for_review(
    invoice_id: int,
    flag_reason: str,
    recommended_action: str,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Flag an invoice for fraud review

    Args:
        invoice_id: The ID of the invoice to flag
        flag_reason: Reason for flagging (e.g., 'suspicious_amount', 'duplicate', 'vendor_risk')
        recommended_action: Recommended action ('hold', 'reject', 'escalate')
        agent_notes: Detailed fraud assessment notes
        session_context: The session context

    Returns:
        Dictionary containing flagged invoice details
    """
    logger.info(
        "Flagging invoice_id: %s for review. Reason: %s, Action: %s",
        invoice_id,
        flag_reason,
        recommended_action,
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
        fraud_note = (
            f"[Fraud Agent] FLAG: {flag_reason}. "
            f"Recommended action: {recommended_action}. "
            f"{agent_notes}"
        )
        new_notes = f"{existing_notes}\n\n{fraud_note}"

        new_status = invoice.status
        if recommended_action == "reject" and invoice.status in (
            "submitted",
            "processing",
        ):
            new_status = "rejected"

        invoice = invoice_repo.update_invoice(
            invoice_id, status=new_status, agent_notes=new_notes
        )
        if not invoice:
            raise ValueError("Invoice not found")

        result = invoice.to_dict()
        result["_previous_state"] = previous_state
        result["flag_reason"] = flag_reason
        result["recommended_action"] = recommended_action
        return result


async def update_fraud_agent_notes(
    vendor_id: int,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update agent notes on a vendor for fraud assessment context

    Args:
        vendor_id: The ID of the vendor
        agent_notes: Notes to append
        session_context: The session context

    Returns:
        Dictionary containing updated vendor
    """
    logger.info(
        "Updating fraud agent notes for vendor_id: %s. Notes: %s",
        vendor_id,
        agent_notes,
    )
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")
        existing_notes = vendor.agent_notes or ""
        new_notes = f"{existing_notes}\n\n[Fraud Agent] {agent_notes}"
        vendor = vendor_repo.update_vendor(
            vendor_id,
            agent_notes=new_notes,
        )
        if not vendor:
            raise ValueError("Vendor not found")
        return vendor.to_dict()
