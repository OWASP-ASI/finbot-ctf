"""FinMail data models -- unified email/message storage.

A single Email model. The inbox_type field ("vendor" or "admin") determines which portal inbox
displays the message. This field is set by application routing logic, never
by LLMs or agents.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
)
from sqlalchemy import DateTime as _DateTime
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from finbot.core.data.database import Base

DateTime = _DateTime(timezone=True)


class Email(Base):
    """Unified email message for vendor and admin inboxes."""

    __tablename__ = "emails"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    # Inbox routing (set by app logic, not LLMs)
    inbox_type = Column[str](String(10), nullable=False)  # "vendor" or "admin"
    vendor_id = Column[int](Integer, ForeignKey("vendors.id"), nullable=True)

    direction = Column[str](String(10), nullable=False, default="outbound")
    message_type = Column[str](String(50), nullable=False)
    channel = Column[str](String(20), nullable=False, default="email")
    subject = Column[str](String(500), nullable=False)
    body = Column[str](Text, nullable=False)

    sender_name = Column[str](String(255), nullable=False)
    sender_type = Column[str](String(20), nullable=False, default="agent")
    from_address = Column[str](String(255), nullable=True)

    # Email addressing (JSON arrays of email strings)
    to_addresses = Column[str](Text, nullable=True)
    cc_addresses = Column[str](Text, nullable=True)
    bcc_addresses = Column[str](Text, nullable=True)
    recipient_role = Column[str](String(10), nullable=True)  # "to", "cc", or "bcc"

    is_read = Column[bool](Boolean, default=False)
    read_at = Column[datetime](DateTime, nullable=True)

    related_invoice_id = Column[int](Integer, ForeignKey("invoices.id"), nullable=True)
    metadata_json = Column[str](Text, nullable=True)

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))

    vendor = relationship("Vendor", foreign_keys=[vendor_id])
    related_invoice = relationship("Invoice", foreign_keys=[related_invoice_id])

    __table_args__ = (
        Index("idx_email_namespace_inbox", "namespace", "inbox_type"),
        Index("idx_email_namespace_vendor", "namespace", "inbox_type", "vendor_id"),
        Index("idx_email_namespace_read", "namespace", "inbox_type", "is_read"),
        Index("idx_email_namespace_type", "namespace", "inbox_type", "message_type"),
        Index("idx_email_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Email(id={self.id}, inbox={self.inbox_type}, type='{self.message_type}')>"

    def _parse_addresses(self, raw: str | None) -> list[str] | None:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "inbox_type": self.inbox_type,
            "vendor_id": self.vendor_id,
            "direction": self.direction,
            "message_type": self.message_type,
            "channel": self.channel,
            "subject": self.subject,
            "body": self.body,
            "sender_name": self.sender_name,
            "sender_type": self.sender_type,
            "from_address": self.from_address,
            "to_addresses": self._parse_addresses(self.to_addresses),
            "cc_addresses": self._parse_addresses(self.cc_addresses),
            "bcc_addresses": self._parse_addresses(self.bcc_addresses),
            "recipient_role": self.recipient_role,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat().replace("+00:00", "Z") if self.read_at else None,
            "related_invoice_id": self.related_invoice_id,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else None,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
        }

    def to_summary_dict(self, preview_length: int = 150) -> dict:
        """Summary representation for list/search results -- body is truncated."""
        body_text = self.body or ""
        if len(body_text) > preview_length:
            body_preview = body_text[:preview_length] + "..."
        else:
            body_preview = body_text

        return {
            "id": self.id,
            "inbox_type": self.inbox_type,
            "vendor_id": self.vendor_id,
            "message_type": self.message_type,
            "subject": self.subject,
            "body_preview": body_preview,
            "sender_name": self.sender_name,
            "from_address": self.from_address,
            "to_addresses": self._parse_addresses(self.to_addresses),
            "is_read": self.is_read,
            "related_invoice_id": self.related_invoice_id,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
        }
