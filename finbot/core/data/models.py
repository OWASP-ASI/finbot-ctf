"""FinBot Data Models"""

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.orm import relationship

from finbot.core.data.database import Base

# Always use TIMESTAMP WITH TIME ZONE so PostgreSQL round-trips
# timezone-aware datetimes without implicit conversion to session TZ.
# SQLite is unaffected (stores ISO-8601 text either way).
DateTime = _DateTime(timezone=True)


# General Models
class User(Base):
    """User Model"""

    __tablename__ = "users"

    id = Column[int](Integer, primary_key=True, index=True)
    user_id = Column[str](String(32), unique=True, nullable=False, index=True)
    email = Column[str](String(255), unique=True, nullable=True, index=True)
    display_name = Column[str](String(100), nullable=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    created_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_login = Column[datetime](DateTime, nullable=True)
    is_active = Column[bool](Boolean, default=True)

    __table_args__ = (
        Index("idx_users_namespace", "namespace"),
        Index("idx_users_email", "email"),
    )

    def __repr__(self) -> str:
        """Return string representation of User for __str__"""
        return f"<User(user_id='{self.user_id}', namespace='{self.namespace}')>"


class UserProfile(Base):
    """User Profile for public sharing and social features.
    Linked to User by user_id. Usernames are globally unique for public URLs.
    """

    __tablename__ = "user_profiles"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    user_id = Column[str](
        String(32), ForeignKey("users.user_id"), unique=True, nullable=False, index=True
    )

    # Public identity
    username = Column[str](String(32), unique=True, nullable=True, index=True)
    bio = Column[str](String(300), nullable=True)
    avatar_emoji = Column[str](String(10), default="🦊")
    avatar_type = Column[str](
        String(10), default="emoji"
    )  # "emoji" | "gravatar" | "url"
    avatar_url = Column[str](
        String(500), nullable=True
    )  # only for avatar_type == "url"

    # Social links
    social_github = Column(String(200), nullable=True)
    social_hackerone = Column(String(200), nullable=True)
    social_bugcrowd = Column(String(200), nullable=True)
    social_twitter = Column(String(200), nullable=True)
    social_linkedin = Column(String(200), nullable=True)
    social_website = Column(String(200), nullable=True)

    # Privacy settings (public by default per user preference)
    is_public = Column[bool](Boolean, default=True)
    show_activity = Column[bool](Boolean, default=False)  # Activity feed is opt-in

    # Featured badges (user picks up to 6 badge IDs to showcase)
    featured_badge_ids = Column[str](Text, nullable=True)  # JSON array of badge IDs

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    user = relationship("User", backref="profile", uselist=False)

    __table_args__ = (
        Index("idx_user_profiles_username", "username"),
        Index("idx_user_profiles_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<UserProfile(user_id='{self.user_id}', username='{self.username}')>"

    def get_featured_badge_ids(self) -> list[str]:
        """Get list of featured badge IDs"""
        if not self.featured_badge_ids:
            return []
        return json.loads(self.featured_badge_ids)

    def set_featured_badge_ids(self, badge_ids: list[str]) -> None:
        """Set featured badge IDs (max 6)"""
        self.featured_badge_ids = json.dumps(badge_ids[:6])

    def to_dict(self) -> dict:
        """Convert profile to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "bio": self.bio,
            "avatar_emoji": self.avatar_emoji,
            "avatar_type": self.avatar_type or "emoji",
            "avatar_url": self.avatar_url,
            "is_public": self.is_public,
            "show_activity": self.show_activity,
            "featured_badge_ids": self.get_featured_badge_ids(),
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z")
            if self.updated_at
            else None,
        }


class UserSession(Base):
    """User Session Model
    - HMAC signatures
    - Namespace isolation for multi-user environments
    """

    __tablename__ = "user_sessions"

    session_id = Column[str](String(64), primary_key=True, index=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    # User ID
    user_id = Column[str](String(32), nullable=False, index=True)
    email = Column[str](String(255), nullable=True, index=True)
    is_temporary = Column[bool](Boolean, default=True)

    # Session data
    session_data = Column[str](Text, nullable=False)  # JSON
    signature = Column[str](String(64), nullable=False)  # HMAC signature
    user_agent = Column[str](String(500), nullable=True)
    last_rotation = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    rotation_count = Column[int](Integer, default=0)
    strict_fingerprint = Column[str](String(32), nullable=True)
    loose_fingerprint = Column[str](String(32), nullable=True)
    original_ip = Column[str](String(45), nullable=True)
    current_ip = Column[str](String(45), nullable=True)
    current_vendor_id = Column[int](
        Integer, ForeignKey("vendors.id"), nullable=True, index=True
    )

    created_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_accessed = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at = Column[datetime](DateTime, nullable=False)

    current_vendor = relationship(
        "Vendor", foreign_keys=[current_vendor_id], back_populates="user_sessions"
    )

    __table_args__ = (
        Index("idx_user_sessions_namespace", "namespace"),
        Index("idx_user_sessions_user_id", "user_id"),
        Index("idx_user_sessions_expires", "expires_at"),
        Index("idx_user_sessions_rotation", "last_rotation"),
        Index("idx_user_sessions_vendor", "namespace", "current_vendor_id"),
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


class MagicLinkToken(Base):
    """Magic Link Token for password-less authentication"""

    __tablename__ = "magic_link_tokens"

    id = Column[int](Integer, primary_key=True)
    token = Column[str](String(64), unique=True, nullable=False, index=True)
    email = Column[str](String(255), nullable=False, index=True)
    session_id = Column[str](String(64), nullable=True)  # Temp session to upgrade

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column[datetime](DateTime, nullable=False)
    used_at = Column[datetime](DateTime, nullable=True)
    ip_address = Column[str](String(45), nullable=True)

    __table_args__ = (
        Index("idx_magic_link_token", "token"),
        Index("idx_magic_link_email", "email"),
        Index("idx_magic_link_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MagicLinkToken(email='{self.email}', used={self.used_at is not None})>"
        )

    def is_expired(self) -> bool:
        """Check if token is expired"""
        now = datetime.now(UTC)
        expires_at = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=UTC)
        )
        return now > expires_at

    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)"""
        return not self.is_expired() and self.used_at is None


# Vendor Portal
class Vendor(Base):
    """Vendor Model"""

    __tablename__ = "vendors"

    id = Column[int](Integer, primary_key=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    # Company Information
    company_name = Column[str](String(255), nullable=False)
    vendor_category = Column[str](String(100), nullable=False)
    industry = Column[str](String(100), nullable=False)
    services = Column[str](Text, nullable=False)

    # Contact Information
    contact_name = Column[str](String(255), nullable=False)
    email = Column[str](String(255), nullable=False)
    phone = Column[str](String(50), nullable=True)

    # Financial Information
    tin = Column[str](String(20), nullable=False)  # Tax ID/EIN
    bank_account_number = Column[str](String(50), nullable=False)
    bank_name = Column[str](String(255), nullable=False)
    bank_routing_number = Column[str](String(20), nullable=False)
    bank_account_holder_name = Column[str](String(255), nullable=False)

    # Metadata
    status = Column[Literal["pending", "active", "inactive"]](
        String(50), default="pending"
    )
    trust_level = Column[Literal["low", "standard", "high"]](String(20), default="low")
    risk_level = Column[Literal["low", "medium", "high"]](String(20), default="high")

    # agent_notes are notes from the agent that processed the vendor
    # Notes are contributed by both AI agents and Human agents
    agent_notes = Column[str](Text, nullable=True)
    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # relationships
    invoices = relationship("Invoice", back_populates="vendor")
    user_sessions = relationship(
        "UserSession",
        foreign_keys="UserSession.current_vendor_id",
        back_populates="current_vendor",
    )

    __table_args__ = (
        UniqueConstraint("namespace", "email", name="uq_vendors_namespace_email"),
        Index("idx_vendors_namespace", "namespace"),
        Index("idx_vendors_namespace_status", "namespace", "status"),
        Index("idx_vendors_email", "email"),
        Index("idx_vendors_category", "vendor_category"),
    )

    def to_dict(self) -> dict:
        """Convert vendor to dictionary"""
        return {
            "id": self.id,
            "company_name": self.company_name,
            "namespace": self.namespace,
            "vendor_category": self.vendor_category,
            "industry": self.industry,
            "services": self.services,
            "contact_name": self.contact_name,
            "email": self.email,
            "phone": self.phone,
            "tin": self.tin,
            "bank_account_number": self.bank_account_number,
            "bank_name": self.bank_name,
            "bank_routing_number": self.bank_routing_number,
            "bank_account_holder_name": self.bank_account_holder_name,
            "status": self.status,
            "agent_notes": self.agent_notes,
            "trust_level": self.trust_level,
            "risk_level": self.risk_level,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }

    def __repr__(self) -> str:
        return f"<Vendor(id='{self.id}', company_name='{self.company_name}', namespace='{self.namespace}')>"


class Invoice(Base):
    """Invoice Model"""

    __tablename__ = "invoices"

    id = Column[int](Integer, primary_key=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    # Invoice data
    vendor_id = Column[int](Integer, ForeignKey("vendors.id"), nullable=False)
    invoice_number = Column[str](String(100), nullable=True)
    amount = Column[Float](Float, nullable=False)
    description = Column[str](Text, nullable=True)
    invoice_date = Column[datetime](DateTime, nullable=False)
    due_date = Column[datetime](DateTime, nullable=False)
    # status is one of: submitted, processing, approved, rejected, paid
    status = Column[Literal["submitted", "processing", "approved", "rejected", "paid"]](
        String(50), default="submitted"
    )
    # agent_notes are notes from the agent that processed the invoice
    # Notes are contributed by both AI agents and Human agents
    agent_notes = Column[str](Text, nullable=True)
    # JSON list of FinDrive file attachments: [{"file_id": 5, "filename": "...", "file_type": "pdf"}]
    attachments = Column[str](Text, nullable=True)

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    vendor = relationship("Vendor", back_populates="invoices")

    __table_args__ = (
        Index("idx_invoices_namespace", "namespace"),
        Index("idx_invoices_namespace_vendor", "namespace", "vendor_id"),
        Index("idx_invoices_namespace_status", "namespace", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation of Invoice for __str__"""
        return f"<Invoice(id={self.id}, amount={self.amount}, namespace='{self.namespace}')>"

    def to_dict(self) -> dict:
        """Convert invoice to dictionary"""
        attachments = []
        if self.attachments:
            try:
                attachments = json.loads(self.attachments)
            except (ValueError, TypeError):
                pass

        return {
            "id": self.id,
            "namespace": self.namespace,
            "vendor_id": self.vendor_id,
            "invoice_number": self.invoice_number,
            "amount": self.amount,
            "description": self.description,
            "invoice_date": self.invoice_date.isoformat().replace("+00:00", "Z"),
            "due_date": self.due_date.isoformat().replace("+00:00", "Z"),
            "status": self.status,
            "agent_notes": self.agent_notes,
            "attachments": attachments,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }


# Chat Messages


class ChatMessage(Base):
    """Messages exchanged between vendors and the AI chat assistant"""

    __tablename__ = "chat_messages"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False)
    user_id = Column[str](String(32), nullable=False)
    vendor_id = Column[int](Integer, ForeignKey("vendors.id"), nullable=True)
    role = Column[str](String(20), nullable=False)  # "user", "assistant", "system"
    content = Column[str](Text, nullable=False)
    workflow_id = Column[str](String(64), nullable=True)
    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    cleared_at = Column[datetime](DateTime, nullable=True)

    __table_args__ = (
        Index(
            "idx_chat_ns_user_vendor_ts",
            "namespace",
            "user_id",
            "vendor_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', user_id='{self.user_id[:8]}')>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z")
            if self.created_at
            else None,
        }


# Admin Portal / MCP Models


class MCPServerConfig(Base):
    """Per-namespace MCP server configuration.
    The tool_overrides_json field is the CTF attack surface for tool poisoning --
    users can modify tool descriptions via the admin portal, and these overrides
    are applied when the MCP server is instantiated for an agent run.
    """

    __tablename__ = "mcp_server_configs"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    server_type = Column[str](
        String(50), nullable=False
    )  # "finstripe", "gdrive", "taxcalc"
    display_name = Column[str](String(255), nullable=False)
    enabled = Column[bool](Boolean, default=True, nullable=False)

    # Server-specific settings (payment limits, mock balance, etc.)
    config_json = Column[str](Text, nullable=True)
    # User-modified tool definitions -- the supply chain attack surface
    tool_overrides_json = Column[str](Text, nullable=True)

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("namespace", "server_type", name="uq_mcp_namespace_server"),
        Index("idx_mcp_config_namespace", "namespace"),
        Index("idx_mcp_config_type", "server_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<MCPServerConfig(namespace='{self.namespace}', "
            f"server_type='{self.server_type}', enabled={self.enabled})>"
        )

    def get_config(self) -> dict:
        return json.loads(self.config_json) if self.config_json else {}

    def get_tool_overrides(self) -> dict:
        return json.loads(self.tool_overrides_json) if self.tool_overrides_json else {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "server_type": self.server_type,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "config": self.get_config(),
            "tool_overrides": self.get_tool_overrides(),
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }


class MCPActivityLog(Base):
    """Records MCP protocol messages for the admin portal activity log.
    Helps CTF players understand attack flows and debug injections.
    """

    __tablename__ = "mcp_activity_log"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)

    server_type = Column[str](String(50), nullable=False)
    direction = Column[str](String(10), nullable=False)  # "request" or "response"
    method = Column[str](
        String(100), nullable=False
    )  # "tools/list", "tools/call", etc.
    tool_name = Column[str](String(100), nullable=True)
    payload_json = Column[str](Text, nullable=True)

    workflow_id = Column[str](String(64), nullable=True, index=True)
    duration_ms = Column[float](Float, nullable=True)

    created_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        Index("idx_mcp_activity_namespace", "namespace"),
        Index("idx_mcp_activity_ns_server", "namespace", "server_type"),
        Index("idx_mcp_activity_ns_ts", "namespace", "created_at"),
        Index("idx_mcp_activity_workflow", "workflow_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<MCPActivityLog(id={self.id}, server='{self.server_type}', "
            f"method='{self.method}', direction='{self.direction}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "server_type": self.server_type,
            "direction": self.direction,
            "method": self.method,
            "tool_name": self.tool_name,
            "payload": json.loads(self.payload_json) if self.payload_json else None,
            "workflow_id": self.workflow_id,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
        }


# CTF Models


class Challenge(Base):
    """CTF Challenge Definition - loaded from YAML files
    - These are global entities that are not namespaced
    """

    __tablename__ = "challenges"

    id = Column[str](String(64), primary_key=True)  # e.g., "prompt-injection-basic"
    title = Column[str](String(200), nullable=False)
    description = Column[str](Text, nullable=False)

    # Categorization
    category = Column[str](String(50), nullable=False)
    subcategory = Column[str](String(50), nullable=True)
    difficulty = Column[str](String(20), nullable=False)
    points = Column[int](Integer, default=100)

    # Rich metadata (stored as JSON strings)
    image_url = Column[str](String(500), nullable=True)
    hints = Column[str](Text, nullable=True)  # JSON: [{"cost": 10, "text": "..."}]
    labels = Column[str](
        Text, nullable=True
    )  # JSON: {"owasp_llm": ["LLM01"], "cwe": ["CWE-77"]}
    prerequisites = Column[str](Text, nullable=True)  # JSON: ["challenge-id-1"]
    resources = Column[str](
        Text, nullable=True
    )  # JSON: [{"title": "...", "url": "..."}]

    # Detector configuration
    detector_class = Column[str](
        String(100), nullable=False
    )  # e.g., "PromptInjectionDetector"
    detector_config = Column[str](Text, nullable=True)  # JSON: detector-specific config

    # Scoring modifiers (penalties/bonuses applied on completion)
    scoring = Column[str](Text, nullable=True)  # JSON: {"modifiers": [...]}

    # Status
    is_active = Column[bool](Boolean, default=True)
    order_index = Column[int](Integer, default=0)
    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    user_progress = relationship("UserChallengeProgress", back_populates="challenge")

    __table_args__ = (
        Index("idx_challenges_category", "category"),
        Index("idx_challenges_difficulty", "difficulty"),
        Index("idx_challenges_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Challenge(id='{self.id}', title='{self.title}', difficulty='{self.difficulty}')>"

    def to_dict(self) -> dict:
        """Convert challenge to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "subcategory": self.subcategory,
            "difficulty": self.difficulty,
            "points": self.points,
            "image_url": self.image_url,
            "hints": json.loads(self.hints) if self.hints else [],
            "labels": json.loads(self.labels) if self.labels else {},
            "prerequisites": json.loads(self.prerequisites)
            if self.prerequisites
            else [],
            "resources": json.loads(self.resources) if self.resources else [],
            "detector_class": self.detector_class,
            "scoring": json.loads(self.scoring) if self.scoring else None,
            "is_active": self.is_active,
            "order_index": self.order_index,
        }


class UserChallengeProgress(Base):
    """Tracks each user's progress on each challenge"""

    __tablename__ = "user_challenge_progress"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)
    user_id = Column[str](String(32), nullable=False, index=True)
    challenge_id = Column[str](String(64), ForeignKey("challenges.id"), nullable=False)

    # Progress tracking
    # status: "locked" (prerequisites not met), "available", "in_progress", "completed"
    status = Column[str](String(20), default="available")
    attempts = Column[int](Integer, default=0)
    successful_attempts = Column[int](Integer, default=0)
    failed_attempts = Column[int](Integer, default=0)
    hints_used = Column[int](Integer, default=0)
    hints_cost = Column[int](Integer, default=0)  # Total points deducted for hints

    # Timestamps
    first_attempt_at = Column[datetime](DateTime, nullable=True)
    completed_at = Column[datetime](DateTime, nullable=True)
    completion_time_seconds = Column[int](
        Integer, nullable=True
    )  # Time from first attempt to completion

    # Dedup: only count one attempt per workflow
    last_attempt_workflow_id = Column[str](String(64), nullable=True)

    # Scoring modifier (compound multiplier: 1.0 = full points, 0.5 = half)
    points_modifier = Column[float](Float, default=1.0, nullable=False)

    # Evidence (for audit/display)
    completion_evidence = Column[str](
        Text, nullable=True
    )  # JSON: events that triggered completion
    completion_workflow_id = Column[str](String(64), nullable=True)

    # Last attempt result (for progress tracking / CTF feedback)
    last_attempt_result = Column[str](Text, nullable=True)  # JSON: gate results from last attempt

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    challenge = relationship("Challenge", back_populates="user_progress")

    __table_args__ = (
        Index("idx_ucp_namespace_user", "namespace", "user_id"),
        Index("idx_ucp_namespace_challenge", "namespace", "challenge_id"),
        Index("idx_ucp_namespace_user_status", "namespace", "user_id", "status"),
        UniqueConstraint(
            "namespace", "user_id", "challenge_id", name="uq_user_challenge"
        ),
    )

    def __repr__(self) -> str:
        return f"<UserChallengeProgress(user_id='{self.user_id}', challenge_id='{self.challenge_id}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """Convert progress to dictionary"""
        return {
            "id": self.id,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "challenge_id": self.challenge_id,
            "status": self.status,
            "attempts": self.attempts,
            "successful_attempts": self.successful_attempts,
            "failed_attempts": self.failed_attempts,
            "hints_used": self.hints_used,
            "hints_cost": self.hints_cost,
            "points_modifier": self.points_modifier,
            "first_attempt_at": self.first_attempt_at.isoformat().replace("+00:00", "Z")
            if self.first_attempt_at
            else None,
            "completed_at": self.completed_at.isoformat().replace("+00:00", "Z")
            if self.completed_at
            else None,
            "completion_time_seconds": self.completion_time_seconds,
            "completion_evidence": json.loads(self.completion_evidence)
            if self.completion_evidence
            else None,
            "completion_workflow_id": self.completion_workflow_id,
            "last_attempt_result": json.loads(self.last_attempt_result)
            if self.last_attempt_result
            else None,
        }


class Badge(Base):
    """CTF Badge Definition - loaded from YAML files"""

    __tablename__ = "badges"

    id = Column[str](
        String(64), primary_key=True
    )  # e.g., "first-blood", "vendor-master"
    title = Column[str](String(200), nullable=False)
    description = Column[str](Text, nullable=False)
    category = Column[str](
        String(50), nullable=False
    )  # "achievement", "milestone", "special"

    icon_url = Column[str](String(500), nullable=True)
    rarity = Column[str](
        String(20), default="common"
    )  # "common", "rare", "epic", "legendary"
    points = Column[int](Integer, default=10)

    # Evaluator configuration
    evaluator_class = Column[str](
        String(100), nullable=False
    )  # e.g., "VendorCountEvaluator"
    evaluator_config = Column[str](
        Text, nullable=True
    )  # JSON: evaluator-specific config

    is_active = Column[bool](Boolean, default=True)
    is_secret = Column[bool](Boolean, default=False)  # Hidden until earned
    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    user_badges = relationship("UserBadge", back_populates="badge")

    __table_args__ = (
        Index("idx_badges_category", "category"),
        Index("idx_badges_rarity", "rarity"),
        Index("idx_badges_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Badge(id='{self.id}', title='{self.title}', rarity='{self.rarity}')>"

    def to_dict(self) -> dict:
        """Convert badge to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "icon_url": self.icon_url,
            "rarity": self.rarity,
            "points": self.points,
            "evaluator_class": self.evaluator_class,
            "evaluator_config": json.loads(self.evaluator_config)
            if self.evaluator_config
            else None,
            "is_active": self.is_active,
            "is_secret": self.is_secret,
        }


class UserBadge(Base):
    """Badges earned by users"""

    __tablename__ = "user_badges"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)
    user_id = Column[str](String(32), nullable=False, index=True)
    badge_id = Column[str](String(64), ForeignKey("badges.id"), nullable=False)

    earned_at = Column[datetime](DateTime, default=datetime.now(UTC))
    earning_context = Column[str](Text, nullable=True)  # JSON: what triggered earning
    earning_workflow_id = Column[str](String(64), nullable=True)

    # Relationships
    badge = relationship("Badge", back_populates="user_badges")

    __table_args__ = (
        Index("idx_ub_namespace_user", "namespace", "user_id"),
        Index("idx_ub_namespace_badge", "namespace", "badge_id"),
        UniqueConstraint("namespace", "user_id", "badge_id", name="uq_user_badge"),
    )

    def __repr__(self) -> str:
        return f"<UserBadge(user_id='{self.user_id}', badge_id='{self.badge_id}')>"

    def to_dict(self) -> dict:
        """Convert user badge to dictionary"""
        return {
            "id": self.id,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "badge_id": self.badge_id,
            "earned_at": self.earned_at.isoformat().replace("+00:00", "Z"),
            "earning_context": json.loads(self.earning_context)
            if self.earning_context
            else None,
            "earning_workflow_id": self.earning_workflow_id,
        }


class CTFEvent(Base):
    """Processed events for CTF activity stream display"""

    __tablename__ = "ctf_events"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    external_event_id = Column[str](
        String(128), unique=True, nullable=False
    )  # For idempotency

    namespace = Column[str](String(64), nullable=False, index=True)
    user_id = Column[str](String(32), nullable=False, index=True)
    session_id = Column[str](String(64), nullable=True)
    workflow_id = Column[str](String(64), nullable=True, index=True)
    vendor_id = Column[int](Integer, nullable=True)  # For vendor-scoped events

    # Event classification
    event_category = Column[str](
        String(50), nullable=False
    )  # "business", "agent", "ctf"
    event_type = Column[str](
        String(100), nullable=False
    )  # e.g., "vendor.created", "task_start"
    event_subtype = Column[str](String(100), nullable=True)

    # Display info
    summary = Column[str](String(500), nullable=False)  # Human-readable summary
    details = Column[str](Text, nullable=True)  # JSON: full event data
    severity = Column[str](
        String(20), default="info"
    )  # "info", "warning", "success", "danger"

    # Agent-specific fields (for rich visualization)
    agent_name = Column[str](String(100), nullable=True)
    tool_name = Column[str](String(100), nullable=True)
    llm_model = Column[str](String(100), nullable=True)
    duration_ms = Column[int](Integer, nullable=True)

    timestamp = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        Index("idx_ctf_event_ns_user_ts", "namespace", "user_id", "timestamp"),
        Index("idx_ctf_event_workflow", "workflow_id"),
        Index("idx_ctf_event_ns_vendor", "namespace", "vendor_id"),
        Index("idx_ctf_event_category", "event_category"),
    )

    def __repr__(self) -> str:
        return (
            f"<CTFEvent(id={self.id}, type='{self.event_type}', user='{self.user_id}')>"
        )

    def to_dict(self) -> dict:
        """Convert event to dictionary"""
        return {
            "id": self.id,
            "external_event_id": self.external_event_id,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "vendor_id": self.vendor_id,
            "event_category": self.event_category,
            "event_type": self.event_type,
            "event_subtype": self.event_subtype,
            "summary": self.summary,
            "details": json.loads(self.details) if self.details else None,
            "severity": self.severity,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "llm_model": self.llm_model,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
        }


# =============================================================================
# Labs Guardrail Config
# =============================================================================


class LabsGuardrailConfig(Base):
    """Per-namespace guardrail webhook configuration for FinBot Labs.

    Stores the user's webhook endpoint, signing secret, per-hook toggles,
    and timeout override. One row per (namespace, user_id).
    """

    __tablename__ = "labs_guardrail_configs"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)
    user_id = Column[str](String(32), nullable=False, index=True)

    webhook_url = Column[str](String(2048), nullable=False)
    signing_secret = Column[str](String(128), nullable=False)
    enabled = Column[bool](Boolean, default=True, nullable=False)

    # Per-hook toggles stored as JSON: {"before_model": true, "after_tool": false, ...}
    hooks_json = Column[str](Text, nullable=True)

    timeout_seconds = Column[int](Integer, default=5, nullable=False)

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "namespace", "user_id", name="uq_labs_guardrail_namespace_user"
        ),
        Index("idx_labs_guardrail_namespace", "namespace"),
        Index("idx_labs_guardrail_user", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<LabsGuardrailConfig(namespace='{self.namespace}', "
            f"user_id='{self.user_id}', enabled={self.enabled})>"
        )

    def get_hooks(self) -> dict[str, bool]:
        if self.hooks_json:
            return json.loads(self.hooks_json)
        return {
            "before_model": True,
            "after_model": True,
            "before_tool": True,
            "after_tool": True,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "webhook_url": self.webhook_url,
            "enabled": self.enabled,
            "hooks": self.get_hooks(),
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z")
            if self.created_at
            else None,
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z")
            if self.updated_at
            else None,
        }


# Non DB Models: Pydantic Models

LLMProviderType = Literal["openai", "http", "mock", "ollama"]


class LLMRequest(BaseModel):
    """LLM Request Model
    - LLM requests are normalized to this internal representation to facilitate multiple providers
    """

    messages: list[dict[str, Any]] | None = None  # input conversation messages
    model: str | None = None  # model to use for the request
    temperature: float | None = None  # temperature to use
    tools: list[dict[str, Any]] | None = None
    provider: LLMProviderType | None = None
    metadata: dict | None = None  # provider specific metadata
    previous_response_id: str | None = None  # stateful chaining where appropriate
    output_json_schema: dict[str, Any] | None = None  # required fields: name, schema


class LLMResponse(BaseModel):
    """LLM Response Model
    - LLM responses are normalized to this internal representation to facilitate multiple providers
    """

    content: str | None = None  # the text output from the model if any
    tool_calls: list[dict] | None = None  # dict of functions and arguments to pass
    success: bool = True  # whether the request was successful
    provider: LLMProviderType | None = None
    metadata: dict | None = None  # provider specific metadata
    messages: list[dict[str, Any]] | None = None  # message history
