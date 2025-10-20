"""Data Repositories for FinBot CTF Platform"""

import json
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from finbot.core.auth.session import SessionContext
from finbot.core.data.models import Invoice, UserActivity, Vendor


class NamespacedRepository:
    """Base Repository for automatic isolation and activity logging"""

    def __init__(self, db: Session, session_context: SessionContext):
        self.db = db
        self.namespace = session_context.namespace
        self.session_context = session_context

    def _add_namespace_filter(self, query, model):
        """Add namespace filter to all queries"""
        return query.filter(model.namespace == self.namespace)

    def _ensure_namespace(self, obj) -> None:
        """Ensure object has correct namespace before saving"""
        if hasattr(obj, "namespace"):
            obj.namespace = self.namespace

    def log_activity(
        self,
        activity_type: str,
        description: str,
        metadata: dict | None = None,
        commit: bool = False,
    ) -> UserActivity:
        """Log user activity

        Args:
            activity_type: Type of activity being logged
            description: Human-readable description
            metadata: Optional metadata dictionary
            commit: Whether to commit immediately (default: False, relies on caller to commit)
        """
        activity = UserActivity(
            namespace=self.namespace,
            user_id=self.session_context.user_id,
            activity_type=activity_type,
            description=description,
            activity_metadata=json.dumps(metadata) if metadata else None,
        )

        self.db.add(activity)
        if commit:
            self.db.commit()
            self.db.refresh(activity)

        return activity


class VendorRepository(NamespacedRepository):
    """Repository for Vendor model"""

    def create_vendor(
        self,
        company_name: str,
        vendor_category: str,
        industry: str,
        services: str,
        contact_name: str,
        email: str,
        tin: str,
        bank_account_number: str,
        bank_name: str,
        bank_routing_number: str,
        bank_account_holder_name: str,
        phone: str | None = None,
    ) -> Vendor:
        """Create a new vendor with all required fields"""
        vendor = Vendor(
            company_name=company_name,
            vendor_category=vendor_category,
            industry=industry,
            services=services,
            contact_name=contact_name,
            email=email,
            tin=tin,
            bank_account_number=bank_account_number,
            bank_name=bank_name,
            bank_routing_number=bank_routing_number,
            bank_account_holder_name=bank_account_holder_name,
            phone=phone,
            namespace=self.namespace,
            status="pending",
        )
        self.db.add(vendor)
        self.db.commit()
        self.db.refresh(vendor)

        self.log_activity(
            "vendor_created",
            f"Created vendor: {company_name}",
            metadata={
                "vendor_id": vendor.id,
                "company_name": company_name,
                "vendor_category": vendor_category,
                "industry": industry,
            },
        )

        return vendor

    def get_vendor(self, vendor_id: int) -> Vendor | None:
        """Get vendor by id"""
        return self._add_namespace_filter(
            self.db.query(Vendor).filter(Vendor.id == vendor_id), Vendor
        ).first()

    def list_vendors(self, status: str | None = None) -> list[Vendor] | None:
        """List vendors"""
        query = self._add_namespace_filter(self.db.query(Vendor), Vendor)

        if status:
            query = query.filter(Vendor.status == status)

        return query.order_by(Vendor.created_at.desc()).all()

    def update_vendor(self, vendor_id: int, **updates) -> Vendor | None:
        """Update vendor"""
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return None

        for key, value in updates.items():
            if hasattr(vendor, key):
                setattr(vendor, key, value)

        vendor.updated_at = datetime.now(UTC)
        self.db.commit()

        self.log_activity(
            "vendor_updated",
            f"Updated vendor: {vendor.name}",
            metadata={
                "vendor_id": vendor.id,
                "vendor_name": vendor.name,
                "updates": list(updates.keys()),
            },
        )

        return vendor

    def delete_vendor(self, vendor_id: int) -> bool:
        """Delete vendor"""
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return False

        vendor_name = vendor.name
        vendor_id = vendor.id
        self.db.delete(vendor)
        self.db.commit()

        self.log_activity(
            "vendor_deleted",
            f"Deleted vendor: {vendor_name}",
            metadata={"vendor_id": vendor_id, "vendor_name": vendor_name},
        )

        return True

    def get_vendor_count(self) -> int:
        """Get count of vendors"""
        return self._add_namespace_filter(self.db.query(Vendor), Vendor).count()


class InvoiceRepository(NamespacedRepository):
    """Repository for Invoice model"""

    def create_invoice(
        self,
        vendor_id: int,
        amount: float,
        invoice_number: str | None = None,
        description: str | None = None,
        pdf_path: str | None = None,
    ) -> Invoice:
        """Create invoice"""

        # Verify vendor exists in same namespace
        vendor_repo = VendorRepository(self.db, self.session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError(f"Vendor {vendor_id} not found in user's namespace")

        invoice = Invoice(
            namespace=self.namespace,
            vendor_id=vendor_id,
            invoice_number=invoice_number,
            amount=amount,
            description=description,
            pdf_path=pdf_path,
            status="processing",
        )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        self.log_activity(
            "invoice_created",
            f"Created invoice for ${amount}",
            metadata={
                "invoice_id": invoice.id,
                "vendor_id": vendor_id,
                "amount": amount,
                "invoice_number": invoice_number,
            },
        )

        return invoice

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        """Get invoice"""
        return self._add_namespace_filter(
            self.db.query(Invoice).filter(Invoice.id == invoice_id), Invoice
        ).first()

    def list_invoices(
        self, vendor_id: int | None = None, status: str | None = None
    ) -> list[Invoice] | None:
        """List invoices"""
        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)

        if vendor_id:
            query = query.filter(Invoice.vendor_id == vendor_id)

        if status:
            query = query.filter(Invoice.status == status)

        return query.order_by(Invoice.created_at.desc()).all()

    def update_invoice_data(
        self, invoice_id: int, extracted_data: str, status: str = "processed"
    ) -> Invoice | None:
        """Update invoice with extracted data"""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            return None

        invoice.extracted_data = extracted_data
        invoice.status = status
        invoice.updated_at = datetime.now(UTC)

        self.db.commit()

        self.log_activity(
            "invoice_processed",
            f"Processed invoice #{invoice.id}",
            metadata={
                "invoice_id": invoice.id,
                "status": status,
                "has_extracted_data": bool(extracted_data),
            },
        )

        return invoice

    def get_invoice_stats(self) -> dict:
        """Get invoice statistics"""
        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)

        total_count = query.count()
        total_amount = query.with_entities(func.sum(Invoice.amount)).scalar() or 0

        status_counts = {}
        for status, count in (
            query.with_entities(Invoice.status, func.count(Invoice.id))
            .group_by(Invoice.status)
            .all()
        ):
            status_counts[status] = count

        return {
            "total_invoices": total_count,
            "total_amount": float(total_amount),
            "status_breakdown": status_counts,
        }


class UserActivityRepository(NamespacedRepository):
    """User activity tracking repository"""

    def log_activity(
        self,
        activity_type: str,
        description: str,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> UserActivity:
        """Log user activity with immediate commit by default"""

        activity = UserActivity(
            namespace=self.namespace,
            user_id=self.session_context.user_id,
            activity_type=activity_type,
            description=description,
            activity_metadata=json.dumps(metadata) if metadata else None,
        )

        self.db.add(activity)
        if commit:
            self.db.commit()
            self.db.refresh(activity)

        return activity

    def get_user_activities(self, limit: int = 50) -> list[UserActivity]:
        """Get user activities in their namespace"""
        return (
            self._add_namespace_filter(
                self.db.query(UserActivity).filter(
                    UserActivity.user_id == self.session_context.user_id
                ),
                UserActivity,
            )
            .order_by(UserActivity.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_activity_stats(self) -> dict:
        """Get activity statistics for user"""
        query = self._add_namespace_filter(
            self.db.query(UserActivity).filter(
                UserActivity.user_id == self.session_context.user_id
            ),
            UserActivity,
        )

        total_activities = query.count()

        activity_types = {}
        activity_type_query = (
            query.with_entities(UserActivity.activity_type)
            .group_by(UserActivity.activity_type)
            .all()
        )
        for activity_type_result in activity_type_query:
            activity_type = activity_type_result[0]
            count = query.filter(UserActivity.activity_type == activity_type).count()
            activity_types[activity_type] = count

        return {"total_activities": total_activities, "activity_types": activity_types}
