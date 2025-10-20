"""FinBot Data Models"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text

from finbot.core.data.database import Base


class User(Base):
    """User Model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(32), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    display_name = Column(String(100), nullable=True)
    namespace = Column(String(64), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_users_namespace", "namespace"),
        Index("idx_users_email", "email"),
    )

    def __repr__(self) -> str:
        """Return string representation of User for __str__"""
        return f"<User(user_id='{self.user_id}', namespace='{self.namespace}')>"


class UserSession(Base):
    """User Session Model
    - HMAC signatures
    - Namespace isolation for multi-user environments
    """

    __tablename__ = "user_sessions"

    session_id = Column(String(64), primary_key=True, index=True)
    namespace = Column(String(64), nullable=False, index=True)

    # User ID
    user_id = Column(String(32), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    is_temporary = Column(Boolean, default=True)

    # Session data
    session_data = Column(Text, nullable=False)  # JSON
    signature = Column(String(64), nullable=False)  # HMAC signature
    user_agent = Column(String(500), nullable=True)
    last_rotation = Column(DateTime, default=datetime.now(UTC))
    rotation_count = Column(Integer, default=0)
    strict_fingerprint = Column(String(32), nullable=True)
    loose_fingerprint = Column(String(32), nullable=True)
    original_ip = Column(String(45), nullable=True)
    current_ip = Column(String(45), nullable=True)

    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)
    last_accessed = Column(DateTime, default=datetime.now(UTC), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_user_sessions_namespace", "namespace"),
        Index("idx_user_sessions_user_id", "user_id"),
        Index("idx_user_sessions_expires", "expires_at"),
        Index("idx_user_sessions_rotation", "last_rotation"),
    )

    def __repr__(self) -> str:
        """Return string representation of UserSession for __str__"""
        return f"<UserSession(session_id='{self.session_id}', namespace='{self.namespace}')>"

    def is_expired(self) -> bool:
        """Check if session is expired"""
        now = datetime.now(UTC)
        # Ensure expires_at is timezone-aware
        expires_at = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=UTC)
        )
        return now > expires_at

    def to_dict(self) -> dict:
        """Convert session to dictionary"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "email": self.email,
            "is_temporary": self.is_temporary,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "last_accessed": self.last_accessed.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
        }


class Vendor(Base):
    """Vendor Model"""

    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    namespace = Column(String(64), nullable=False, index=True)

    # Company Information
    company_name = Column(String(255), nullable=False)
    vendor_category = Column(String(100), nullable=False)
    industry = Column(String(100), nullable=False)
    services = Column(Text, nullable=False)

    # Contact Information
    contact_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)

    # Financial Information
    tin = Column(String(20), nullable=False)  # Tax ID/EIN
    bank_account_number = Column(String(50), nullable=False)
    bank_name = Column(String(255), nullable=False)
    bank_routing_number = Column(String(20), nullable=False)
    bank_account_holder_name = Column(String(255), nullable=False)

    # Metadata
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

    __table_args__ = (
        Index("idx_vendors_namespace", "namespace"),
        Index("idx_vendors_namespace_status", "namespace", "status"),
        Index("idx_vendors_email", "email"),
        Index("idx_vendors_category", "vendor_category"),
    )

    def __repr__(self) -> str:
        return f"<Vendor(id='{self.id}', company_name='{self.company_name}', namespace='{self.namespace}')>"


class Invoice(Base):
    """Invoice Model"""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    namespace = Column(String(64), nullable=False, index=True)

    # Invoice data
    vendor_id = Column(Integer, nullable=False)  # References vendor in same namespace
    invoice_number = Column(String(100), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending")

    # File information
    pdf_path = Column(String(500), nullable=True)
    extracted_data = Column(Text, nullable=True)  # JSON

    created_at = Column(DateTime, default=datetime.now(UTC))
    updated_at = Column(DateTime, default=datetime.now(UTC), onupdate=datetime.now(UTC))

    __table_args__ = (
        Index("idx_invoices_namespace", "namespace"),
        Index("idx_invoices_namespace_vendor", "namespace", "vendor_id"),
        Index("idx_invoices_namespace_status", "namespace", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation of Invoice for __str__"""
        return f"<Invoice(id={self.id}, amount={self.amount}, namespace='{self.namespace}')>"


class UserActivity(Base):
    """User Activity Model
    - Useful for auditing, compliance and CTF purposes
    """

    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True)
    namespace = Column(String(64), nullable=False, index=True)

    # activity data
    user_id = Column(String(32), nullable=False)
    activity_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    activity_metadata = Column(Text, nullable=True)  # JSON

    created_at = Column(DateTime, default=datetime.now(UTC))
    __table_args__ = (
        Index("idx_activities_namespace", "namespace"),
        Index("idx_activities_namespace_user", "namespace", "user_id"),
        Index("idx_activities_namespace_type", "namespace", "activity_type"),
    )
