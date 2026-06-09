"""FinStripe data models -- payment transactions processed through the mock Stripe MCP server."""

import json
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column
from sqlalchemy import DateTime as _DateTime
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from finbot.core.data.database import Base

DateTime = _DateTime(timezone=True)


class PaymentTransaction(Base):
    """Records fund transfers processed through the FinStripe MCP server.
    Separate from invoice status -- tracks the actual money movement.
    """

    __tablename__ = "payment_transactions"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    invoice_id = Column[int](Integer, ForeignKey("invoices.id"), nullable=False)
    vendor_id = Column[int](Integer, ForeignKey("vendors.id"), nullable=False)

    transfer_id = Column[str](String(100), unique=True, nullable=False, index=True)
    amount = Column[float](Float, nullable=False)
    currency = Column[str](String(10), nullable=False, default="usd")
    payment_method = Column[str](String(50), nullable=False)
    status = Column[Literal["pending", "completed", "failed"]](
        String(20), nullable=False, default="pending"
    )

    # In CTF, tool poisoning may cause agents to leak sensitive data
    # (e.g., bank routing numbers) into this field
    description = Column[str](Text, nullable=True)
    metadata_json = Column[str](Text, nullable=True)

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    invoice = relationship("Invoice", foreign_keys=[invoice_id])
    vendor = relationship("Vendor", foreign_keys=[vendor_id])

    __table_args__ = (
        Index("idx_ptx_namespace", "namespace"),
        Index("idx_ptx_namespace_vendor", "namespace", "vendor_id"),
        Index("idx_ptx_namespace_invoice", "namespace", "invoice_id"),
        Index("idx_ptx_transfer_id", "transfer_id"),
        Index("idx_ptx_namespace_status", "namespace", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentTransaction(id={self.id}, transfer_id='{self.transfer_id}', "
            f"amount={self.amount}, status='{self.status}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "invoice_id": self.invoice_id,
            "vendor_id": self.vendor_id,
            "transfer_id": self.transfer_id,
            "amount": self.amount,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "status": self.status,
            "description": self.description,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else None,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }
