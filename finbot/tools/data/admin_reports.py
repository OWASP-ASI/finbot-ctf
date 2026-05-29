"""Admin reporting and data aggregation tools for the Finance Co-Pilot.

These tools aggregate data from multiple sources (vendors, invoices, FinDrive,
FinMail) into single responses that the LLM processes for report generation.

The untrusted fields (agent_notes, description, content_text, email body)
deliberately enter the LLM context -- this is the indirect prompt injection
surface for CTF challenges.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository, VendorRepository
from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository
from finbot.mcp.servers.finmail.repositories import EmailRepository

logger = logging.getLogger(__name__)


async def get_all_vendors_summary(
    session_context: SessionContext,
) -> list[dict[str, Any]]:
    """Get all vendors with invoice statistics and agent notes."""
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        invoice_repo = InvoiceRepository(db, session_context)

        vendors = vendor_repo.list_vendors() or []
        result = []

        for vendor in vendors:
            invoices = invoice_repo.list_invoices_for_specific_vendor(vendor.id)

            by_status: dict[str, dict[str, Any]] = {}
            total_amount = 0.0
            for inv in invoices:
                amount = float(inv.amount) if inv.amount else 0.0
                total_amount += amount
                status = inv.status or "unknown"
                if status not in by_status:
                    by_status[status] = {"count": 0, "amount": 0.0}
                by_status[status]["count"] += 1
                by_status[status]["amount"] += amount

            result.append(
                {
                    "vendor_id": vendor.id,
                    "company_name": vendor.company_name,
                    "vendor_category": vendor.vendor_category,
                    "status": vendor.status,
                    "trust_level": vendor.trust_level,
                    "risk_level": vendor.risk_level,
                    "services": vendor.services,
                    "agent_notes": vendor.agent_notes,
                    "email": vendor.email,
                    "invoice_summary": {
                        "total_invoices": len(invoices),
                        "total_amount": total_amount,
                        "by_status": by_status,
                    },
                }
            )

        return result


async def get_pending_actions_summary(
    session_context: SessionContext,
) -> dict[str, Any]:
    """Get all items needing admin attention."""
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        invoice_repo = InvoiceRepository(db, session_context)

        all_vendors = vendor_repo.list_vendors() or []
        all_invoices = invoice_repo.list_all_invoices_for_user()

        pending_vendors = [
            {
                "vendor_id": v.id,
                "company_name": v.company_name,
                "services": v.services,
                "agent_notes": v.agent_notes,
                "created_at": (
                    v.created_at.isoformat().replace("+00:00", "Z") if v.created_at else None
                ),
            }
            for v in all_vendors
            if v.status == "pending"
        ]

        pending_invoices = [
            {
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "vendor_id": inv.vendor_id,
                "amount": float(inv.amount) if inv.amount else 0.0,
                "description": inv.description,
                "agent_notes": inv.agent_notes,
                "status": inv.status,
                "due_date": (
                    inv.due_date.isoformat().replace("+00:00", "Z") if inv.due_date else None
                ),
            }
            for inv in all_invoices
            if inv.status in ("submitted", "processing")
        ]

        high_risk_vendors = [
            {
                "vendor_id": v.id,
                "company_name": v.company_name,
                "status": v.status,
                "trust_level": v.trust_level,
                "risk_level": v.risk_level,
                "agent_notes": v.agent_notes,
            }
            for v in all_vendors
            if v.risk_level == "high"
        ]

        return {
            "pending_vendors": pending_vendors,
            "pending_vendors_count": len(pending_vendors),
            "pending_invoices": pending_invoices,
            "pending_invoices_count": len(pending_invoices),
            "high_risk_vendors": high_risk_vendors,
            "high_risk_vendors_count": len(high_risk_vendors),
        }


async def get_vendor_compliance_docs(
    vendor_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get a vendor's profile and all their FinDrive files with full content."""
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        file_repo = FinDriveFileRepository(db, session_context)

        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        files = file_repo.list_files(vendor_id=vendor_id)

        return {
            "vendor": {
                "vendor_id": vendor.id,
                "company_name": vendor.company_name,
                "vendor_category": vendor.vendor_category,
                "status": vendor.status,
                "trust_level": vendor.trust_level,
                "risk_level": vendor.risk_level,
                "services": vendor.services,
                "industry": vendor.industry,
                "agent_notes": vendor.agent_notes,
            },
            "documents": [
                {
                    "file_id": f.id,
                    "filename": f.filename,
                    "file_type": f.file_type,
                    "folder_path": f.folder_path,
                    "content_text": f.content_text,
                    "created_at": (
                        f.created_at.isoformat().replace("+00:00", "Z") if f.created_at else None
                    ),
                }
                for f in files
            ],
            "document_count": len(files),
        }


async def get_vendor_activity_report(
    vendor_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get comprehensive activity report pulling from every data source."""
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        invoice_repo = InvoiceRepository(db, session_context)
        file_repo = FinDriveFileRepository(db, session_context)
        email_repo = EmailRepository(db, session_context)

        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        invoices = invoice_repo.list_invoices_for_specific_vendor(vendor_id)
        files = file_repo.list_files(vendor_id=vendor_id)
        emails = email_repo.list_vendor_emails(vendor_id=vendor_id, limit=20)

        by_status: dict[str, dict[str, Any]] = {}
        total_amount = 0.0
        for inv in invoices:
            amount = float(inv.amount) if inv.amount else 0.0
            total_amount += amount
            status = inv.status or "unknown"
            if status not in by_status:
                by_status[status] = {"count": 0, "amount": 0.0}
            by_status[status]["count"] += 1
            by_status[status]["amount"] += amount

        return {
            "vendor": {
                "vendor_id": vendor.id,
                "company_name": vendor.company_name,
                "vendor_category": vendor.vendor_category,
                "status": vendor.status,
                "trust_level": vendor.trust_level,
                "risk_level": vendor.risk_level,
                "services": vendor.services,
                "industry": vendor.industry,
                "agent_notes": vendor.agent_notes,
                "email": vendor.email,
                "contact_name": vendor.contact_name,
            },
            "invoices": [
                {
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "amount": float(inv.amount) if inv.amount else 0.0,
                    "status": inv.status,
                    "description": inv.description,
                    "agent_notes": inv.agent_notes,
                    "invoice_date": (
                        inv.invoice_date.isoformat().replace("+00:00", "Z")
                        if inv.invoice_date
                        else None
                    ),
                    "due_date": (
                        inv.due_date.isoformat().replace("+00:00", "Z") if inv.due_date else None
                    ),
                }
                for inv in invoices
            ],
            "payment_summary": {
                "total_invoices": len(invoices),
                "total_amount": total_amount,
                "by_status": by_status,
            },
            "emails": [
                {
                    "email_id": e.id,
                    "subject": e.subject,
                    "body": e.body,
                    "sender_name": e.sender_name,
                    "direction": e.direction,
                    "message_type": e.message_type,
                    "created_at": (
                        e.created_at.isoformat().replace("+00:00", "Z") if e.created_at else None
                    ),
                }
                for e in emails
            ],
            "documents": [
                {
                    "file_id": f.id,
                    "filename": f.filename,
                    "file_type": f.file_type,
                    "folder_path": f.folder_path,
                    "content_text": f.content_text,
                    "created_at": (
                        f.created_at.isoformat().replace("+00:00", "Z") if f.created_at else None
                    ),
                }
                for f in files
            ],
        }


async def save_report(
    title: str,
    content: str,
    report_type: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Save a markdown report as a persistent artifact in FinDrive."""
    with db_session() as db:
        file_repo = FinDriveFileRepository(db, session_context)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_{timestamp}.md"

        f = file_repo.create_file(
            filename=filename,
            content_text=content,
            vendor_id=None,
            content_type="text/markdown",
            file_type="report",
            folder_path="/reports",
        )

        logger.info(
            "Co-Pilot report saved: id=%d, type=%s, title='%s'",
            f.id,
            report_type,
            title,
        )

        return {
            "file_id": f.id,
            "filename": f.filename,
            "report_type": report_type,
            "title": title,
            "viewer_url": f"/admin/findrive#file-{f.id}",
            "status": "saved",
        }
