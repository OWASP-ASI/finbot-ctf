"""Data Repositories for FinBot CTF Platform"""

import ipaddress
import json
import secrets
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from finbot.core.auth.session import SessionContext
from finbot.core.data.models import (
    Badge,
    Challenge,
    ChatMessage,
    CTFEvent,
    Invoice,
    LabsGuardrailConfig,
    MCPActivityLog,
    MCPServerConfig,
    User,
    UserBadge,
    UserChallengeProgress,
    UserProfile,
    Vendor,
)


class NamespacedRepository:
    """Base Repository for namespace isolation (audit trail is event-driven via CTFEvent)."""

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


# =============================================================================
# User Profile Repository
# =============================================================================

# Reserved usernames that cannot be claimed
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "administrator",
        "api",
        "app",
        "auth",
        "badge",
        "badges",
        "challenge",
        "challenges",
        "ctf",
        "dashboard",
        "finbot",
        "h",
        "hack",
        "hacker",
        "help",
        "home",
        "login",
        "logout",
        "me",
        "messages",
        "null",
        "owasp",
        "portal",
        "profile",
        "root",
        "settings",
        "share",
        "static",
        "support",
        "system",
        "test",
        "toolkit",
        "undefined",
        "user",
        "users",
        "vendor",
        "vendors",
        "web",
        "www",
    }
)


def validate_username(username: str) -> tuple[bool, str | None]:
    """Validate username format and rules.

    Returns (is_valid, error_message).
    """
    import re

    if not username:
        return False, "Username is required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters"

    if len(username) > 20:
        return False, "Username must be 20 characters or less"

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", username):
        return (
            False,
            "Username must start with a letter and contain only letters, numbers, and underscores",
        )

    if username.lower() in RESERVED_USERNAMES:
        return False, "This username is reserved"

    return True, None


class UserProfileRepository:
    """Repository for UserProfile - not namespaced, linked to user_id."""

    def __init__(self, db: Session, session_context: SessionContext | None = None):
        self.db = db
        self.session_context = session_context

    def get_by_user_id(self, user_id: str) -> UserProfile | None:
        """Get profile by user_id"""
        return self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    def get_by_username(self, username: str) -> UserProfile | None:
        """Get profile by username (case-insensitive)"""
        return (
            self.db.query(UserProfile)
            .filter(func.lower(UserProfile.username) == username.lower())
            .first()
        )

    def get_current_user_profile(self) -> UserProfile | None:
        """Get profile for current session user"""
        if not self.session_context:
            raise ValueError("Session context required")
        return self.get_by_user_id(self.session_context.user_id)

    def get_or_create_for_current_user(self) -> UserProfile:
        """Get or create profile for current session user"""
        if not self.session_context:
            raise ValueError("Session context required")

        profile = self.get_by_user_id(self.session_context.user_id)
        if not profile:
            profile = UserProfile(
                user_id=self.session_context.user_id,
                is_public=True,
                show_activity=False,
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        return profile

    def is_username_available(
        self, username: str, exclude_user_id: str | None = None
    ) -> bool:
        """Check if username is available"""
        is_valid, _ = validate_username(username)
        if not is_valid:
            return False

        query = self.db.query(UserProfile).filter(
            func.lower(UserProfile.username) == username.lower()
        )
        if exclude_user_id:
            query = query.filter(UserProfile.user_id != exclude_user_id)

        return query.first() is None

    def claim_username(
        self, user_id: str, username: str
    ) -> tuple[UserProfile | None, str | None]:
        """Claim a username for a user.

        Returns (profile, error_message). If successful, error_message is None.
        """
        is_valid, error = validate_username(username)
        if not is_valid:
            return None, error

        if not self.is_username_available(username, exclude_user_id=user_id):
            return None, "This username is already taken"

        profile = self.get_by_user_id(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id, is_public=True)
            self.db.add(profile)

        profile.username = username
        profile.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(profile)

        return profile, None

    def update_profile(
        self,
        user_id: str,
        bio: str | None = None,
        avatar_emoji: str | None = None,
        avatar_type: str | None = None,
        avatar_url: str | None = None,
        is_public: bool | None = None,
        show_activity: bool | None = None,
    ) -> UserProfile | None:
        """Update profile fields"""
        profile = self.get_by_user_id(user_id)
        if not profile:
            return None

        if bio is not None:
            profile.bio = bio[:300] if bio else None
        if avatar_emoji is not None:
            profile.avatar_emoji = avatar_emoji[:10] if avatar_emoji else "🦊"
        if avatar_type is not None and avatar_type in ("emoji", "gravatar", "url"):
            profile.avatar_type = avatar_type
            if avatar_type != "url":
                profile.avatar_url = None
        if avatar_url is not None and profile.avatar_type == "url":
            profile.avatar_url = avatar_url[:500] if avatar_url else None
        if is_public is not None:
            profile.is_public = is_public
        if show_activity is not None:
            profile.show_activity = show_activity

        profile.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(profile)

        return profile

    def set_featured_badges(
        self, user_id: str, badge_ids: list[str]
    ) -> UserProfile | None:
        """Set featured badge IDs (max 6)"""
        profile = self.get_by_user_id(user_id)
        if not profile:
            return None

        profile.set_featured_badge_ids(badge_ids)
        profile.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(profile)

        return profile

    def get_public_profile_with_user(
        self, username: str
    ) -> tuple[UserProfile | None, User | None]:
        """Get public profile with associated user data"""
        profile = self.get_by_username(username)
        if not profile or not profile.is_public:
            return None, None

        user = self.db.query(User).filter(User.user_id == profile.user_id).first()
        return profile, user


# =============================================================================
# Vendor Repository
# =============================================================================


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

        return vendor

    def delete_vendor(self, vendor_id: int) -> bool:
        """Delete vendor"""
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return False

        self.db.delete(vendor)
        self.db.commit()

        return True

    def get_vendor_count(self) -> int:
        """Get count of vendors"""
        return self._add_namespace_filter(self.db.query(Vendor), Vendor).count()

    def set_current_vendor(self, vendor_id: int) -> bool:
        """Set current vendor for user (all sessions)"""
        # Validate vendor belongs to user
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            return False

        # Update vendor context globally
        # avoid circular import; pylint: disable=import-outside-toplevel
        from finbot.core.auth.session import session_manager

        return session_manager.update_vendor_context(
            self.session_context.session_id, vendor_id
        )


# =============================================================================
# Invoice Repository
# =============================================================================


class InvoiceRepository(NamespacedRepository):
    """Invoice repository - Namespaced to user"""

    def __init__(self, db: Session, session_context: SessionContext):
        super().__init__(db, session_context)
        self.current_vendor_id = session_context.current_vendor_id

    # Vendor Scoped Methods for Vendor Portal
    def list_invoices_for_current_vendor(
        self, status: str | None = None
    ) -> list[Invoice]:
        """Vendor portal: List invoices for current vendor only"""
        if not self.current_vendor_id:
            raise ValueError("Vendor context required for this operation")

        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)
        query = query.filter(Invoice.vendor_id == self.current_vendor_id)

        if status:
            query = query.filter(Invoice.status == status)

        return query.order_by(Invoice.created_at.desc()).all()

    def create_invoice_for_current_vendor(self, **invoice_data) -> Invoice:
        """Vendor portal: Create invoice for current vendor"""
        if not self.current_vendor_id:
            raise ValueError("Vendor context required for this operation")

        invoice_data["vendor_id"] = self.current_vendor_id
        invoice_data["namespace"] = self.namespace

        invoice = Invoice(**invoice_data)
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        return invoice

    def get_current_vendor_invoice_stats(self) -> dict:
        """Vendor portal: Get invoice stats for current vendor"""
        if not self.current_vendor_id:
            raise ValueError("Vendor context required for this operation")

        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)
        query = query.filter(Invoice.vendor_id == self.current_vendor_id)

        total_count = query.count()
        total_amount = query.with_entities(func.sum(Invoice.amount)).scalar() or 0
        paid_count = query.filter(Invoice.status == "paid").count()
        paid_amount = (
            query.filter(Invoice.status == "paid")
            .with_entities(func.sum(Invoice.amount))
            .scalar()
            or 0
        )

        # Count overdue invoices (due date passed, not paid)
        now = datetime.now(UTC)
        overdue_query = self._add_namespace_filter(self.db.query(Invoice), Invoice)
        overdue_query = overdue_query.filter(
            Invoice.vendor_id == self.current_vendor_id
        )
        overdue_count = (
            overdue_query.filter(Invoice.status != "paid")
            .filter(Invoice.due_date < now)
            .count()
        )

        pending_count = total_count - paid_count

        return {
            "total_count": total_count,
            "total_amount": float(total_amount),
            "paid_count": paid_count,
            "paid_amount": float(paid_amount),
            "pending_count": pending_count,
            "pending_amount": float(total_amount) - float(paid_amount),
            "overdue_count": overdue_count,
        }

    # Admin Portal Methods (cross-vendor within namespace)
    def list_all_invoices_for_user(self, status: str | None = None) -> list[Invoice]:
        """Admin portal: List ALL invoices across all user's vendors"""
        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)

        if status:
            query = query.filter(Invoice.status == status)

        return query.order_by(Invoice.created_at.desc()).all()

    def list_invoices_by_vendor(
        self, status: str | None = None
    ) -> dict[int, list[Invoice]]:
        """Admin portal: Group invoices by vendor"""
        invoices = self.list_all_invoices_for_user(status)

        grouped = {}
        for invoice in invoices:
            vendor_id = invoice.vendor_id
            if vendor_id not in grouped:
                grouped[vendor_id] = []
            grouped[vendor_id].append(invoice)

        return grouped

    def get_invoice_stats_by_vendor(self) -> dict[int, dict]:
        """Admin portal: Get invoice statistics grouped by vendor"""
        stats = (
            self.db.query(
                Invoice.vendor_id,
                func.count(Invoice.id).label("total_count"),
                func.sum(Invoice.amount).label("total_amount"),
                func.count(func.nullif(Invoice.status != "paid", True)).label(
                    "paid_count"
                ),
                func.sum(
                    func.case([(Invoice.status == "paid", Invoice.amount)], else_=0)
                ).label("paid_amount"),
            )
            .filter(Invoice.namespace == self.namespace)
            .group_by(Invoice.vendor_id)
            .all()
        )

        return {
            stat.vendor_id: {
                "total_count": stat.total_count,
                "total_amount": float(stat.total_amount or 0),
                "paid_count": stat.paid_count,
                "paid_amount": float(stat.paid_amount or 0),
                "pending_count": stat.total_count - stat.paid_count,
                "pending_amount": float(stat.total_amount or 0)
                - float(stat.paid_amount or 0),
            }
            for stat in stats
        }

    def get_user_invoice_totals(self) -> dict:
        """Admin portal: Get aggregate invoice totals for user"""
        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)

        total_count = query.count()
        total_amount = query.with_entities(func.sum(Invoice.amount)).scalar() or 0
        paid_count = query.filter(Invoice.status == "paid").count()
        paid_amount = (
            query.filter(Invoice.status == "paid")
            .with_entities(func.sum(Invoice.amount))
            .scalar()
            or 0
        )

        return {
            "total_count": total_count,
            "total_amount": float(total_amount),
            "paid_count": paid_count,
            "paid_amount": float(paid_amount),
            "pending_count": total_count - paid_count,
            "pending_amount": float(total_amount) - float(paid_amount),
        }

    # Flexible Methods (can be used by both portals)
    def list_invoices_for_specific_vendor(
        self, vendor_id: int, status: str | None = None
    ) -> list[Invoice]:
        """List invoices for specific vendor"""
        # Validate vendor belongs to user's namespace
        vendor_repo = VendorRepository(self.db, self.session_context)
        if not vendor_repo.get_vendor(vendor_id):
            raise ValueError("Vendor not found or access denied")

        query = self._add_namespace_filter(self.db.query(Invoice), Invoice)
        query = query.filter(Invoice.vendor_id == vendor_id)

        if status:
            query = query.filter(Invoice.status == status)

        return query.order_by(Invoice.created_at.desc()).all()

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        """Flexible: Get single invoice (validates namespace, not vendor)"""
        return self._add_namespace_filter(
            self.db.query(Invoice).filter(Invoice.id == invoice_id), Invoice
        ).first()

    def update_invoice(self, invoice_id: int, **updates) -> Invoice | None:
        """Flexible: Update invoice (validates namespace)"""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            return None

        for key, value in updates.items():
            if hasattr(invoice, key):
                setattr(invoice, key, value)

        invoice.updated_at = datetime.now(UTC)
        self.db.commit()

        return invoice


# =============================================================================
# MCP Server Config Repository
# =============================================================================


class MCPServerConfigRepository(NamespacedRepository):
    """Repository for MCPServerConfig -- per-namespace MCP server settings."""

    def get_by_type(self, server_type: str) -> MCPServerConfig | None:
        return (
            self._add_namespace_filter(self.db.query(MCPServerConfig), MCPServerConfig)
            .filter(MCPServerConfig.server_type == server_type)
            .first()
        )

    def list_all(self) -> list[MCPServerConfig]:
        return (
            self._add_namespace_filter(self.db.query(MCPServerConfig), MCPServerConfig)
            .order_by(MCPServerConfig.server_type)
            .all()
        )

    def upsert(
        self,
        server_type: str,
        display_name: str,
        enabled: bool = True,
        config_json: str | None = None,
        tool_overrides_json: str | None = None,
    ) -> MCPServerConfig:
        existing = self.get_by_type(server_type)
        if existing:
            existing.display_name = display_name
            existing.enabled = enabled
            if config_json is not None:
                existing.config_json = config_json
            if tool_overrides_json is not None:
                existing.tool_overrides_json = tool_overrides_json
            existing.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        config = MCPServerConfig(
            namespace=self.namespace,
            server_type=server_type,
            display_name=display_name,
            enabled=enabled,
            config_json=config_json,
            tool_overrides_json=tool_overrides_json,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_config(
        self, server_type: str, config_json: str
    ) -> MCPServerConfig | None:
        config = self.get_by_type(server_type)
        if config:
            config.config_json = config_json
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_tool_overrides(
        self, server_type: str, tool_overrides_json: str
    ) -> MCPServerConfig | None:
        config = self.get_by_type(server_type)
        if config:
            config.tool_overrides_json = tool_overrides_json
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config

    def toggle_enabled(self, server_type: str) -> MCPServerConfig | None:
        config = self.get_by_type(server_type)
        if config:
            config.enabled = not config.enabled
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config

    def reset_tool_overrides(self, server_type: str) -> MCPServerConfig | None:
        config = self.get_by_type(server_type)
        if config:
            config.tool_overrides_json = None
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config


# =============================================================================
# MCP Activity Log Repository
# =============================================================================


class MCPActivityLogRepository(NamespacedRepository):
    """Repository for MCPActivityLog -- MCP protocol message history."""

    def log_activity(
        self,
        server_type: str,
        direction: str,
        method: str,
        tool_name: str | None = None,
        payload_json: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
    ) -> MCPActivityLog:
        entry = MCPActivityLog(
            namespace=self.namespace,
            server_type=server_type,
            direction=direction,
            method=method,
            tool_name=tool_name,
            payload_json=payload_json,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_activity(
        self,
        server_type: str | None = None,
        workflow_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MCPActivityLog]:
        query = self._add_namespace_filter(
            self.db.query(MCPActivityLog), MCPActivityLog
        )
        if server_type:
            query = query.filter(MCPActivityLog.server_type == server_type)
        if workflow_id:
            query = query.filter(MCPActivityLog.workflow_id == workflow_id)
        return (
            query.order_by(MCPActivityLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_activity_count(self, server_type: str | None = None) -> int:
        query = self._add_namespace_filter(
            self.db.query(MCPActivityLog), MCPActivityLog
        )
        if server_type:
            query = query.filter(MCPActivityLog.server_type == server_type)
        return query.count()


# =============================================================================
# CTF Repositories
# =============================================================================

# =============================================================================
# Chat Message Repository
# =============================================================================


class ChatMessageRepository(NamespacedRepository):
    """Repository for ChatMessage -- scoped to current user + vendor."""

    def __init__(self, db: Session, session_context: SessionContext):
        super().__init__(db, session_context)
        self.user_id = session_context.user_id
        self.vendor_id = session_context.current_vendor_id

    def add_message(
        self,
        role: str,
        content: str,
        workflow_id: str | None = None,
    ) -> "ChatMessage":
        msg = ChatMessage(
            namespace=self.namespace,
            user_id=self.user_id,
            vendor_id=self.vendor_id,
            role=role,
            content=content,
            workflow_id=workflow_id,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_history(self, limit: int = 100) -> list["ChatMessage"]:
        query = (
            self._add_namespace_filter(self.db.query(ChatMessage), ChatMessage)
            .filter(ChatMessage.user_id == self.user_id)
            .filter(ChatMessage.cleared_at.is_(None))
        )
        if self.vendor_id:
            query = query.filter(ChatMessage.vendor_id == self.vendor_id)
        else:
            query = query.filter(ChatMessage.vendor_id.is_(None))

        return (
            query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
            .all()
        )[::-1]  # reverse to chronological order

    def clear_history(self) -> int:
        now = datetime.now(UTC)
        query = (
            self._add_namespace_filter(self.db.query(ChatMessage), ChatMessage)
            .filter(ChatMessage.user_id == self.user_id)
            .filter(ChatMessage.cleared_at.is_(None))
        )
        if self.vendor_id:
            query = query.filter(ChatMessage.vendor_id == self.vendor_id)
        else:
            query = query.filter(ChatMessage.vendor_id.is_(None))

        count = query.update({"cleared_at": now})
        self.db.commit()
        return count


# =============================================================================
# Challenge Repository
# =============================================================================


class ChallengeRepository:
    """Repository for Challenge definitions (global, not namespaced)"""

    def __init__(self, db: Session):
        self.db = db

    def list_challenges(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        active_only: bool = True,
    ) -> list[Challenge]:
        """List challenges with optional filters"""
        query = self.db.query(Challenge)

        if active_only:
            query = query.filter(Challenge.is_active == True)
        if category:
            query = query.filter(Challenge.category == category)
        if difficulty:
            query = query.filter(Challenge.difficulty == difficulty)

        return query.order_by(Challenge.order_index, Challenge.id).all()

    def get_challenge(self, challenge_id: str) -> Challenge | None:
        """Get challenge by ID"""
        return self.db.query(Challenge).filter(Challenge.id == challenge_id).first()

    def get_categories(self) -> list[str]:
        """Get distinct challenge categories"""
        result = (
            self.db.query(Challenge.category)
            .filter(Challenge.is_active == True)
            .distinct()
            .all()
        )
        return [r[0] for r in result]

    def count_by_category(self) -> dict[str, int]:
        """Count challenges per category"""
        result = (
            self.db.query(Challenge.category, func.count(Challenge.id))
            .filter(Challenge.is_active == True)
            .group_by(Challenge.category)
            .all()
        )
        return {cat: count for cat, count in result}

    def get_total_points(self, challenge_ids: list[str]) -> int:
        """Get total points for given challenge IDs (ignores modifiers)"""
        if not challenge_ids:
            return 0
        return (
            self.db.query(func.sum(Challenge.points))
            .filter(Challenge.id.in_(challenge_ids))
            .scalar()
            or 0
        )

    def get_effective_points(
        self,
        completed_progress: list["UserChallengeProgress"],
    ) -> int:
        """Get total effective points applying per-completion modifiers.

        effective = SUM(challenge.points * progress.points_modifier)
        """
        if not completed_progress:
            return 0
        challenge_ids = [p.challenge_id for p in completed_progress]
        challenges = (
            self.db.query(Challenge).filter(Challenge.id.in_(challenge_ids)).all()
        )
        points_map = {c.id: c.points for c in challenges}
        total = 0.0
        for p in completed_progress:
            base = points_map.get(p.challenge_id, 0)
            total += base * (
                p.points_modifier if p.points_modifier is not None else 1.0
            )
        return int(total)


# =============================================================================
# User Challenge Progress Repository
# =============================================================================


class UserChallengeProgressRepository(NamespacedRepository):
    """Repository for user challenge progress (namespaced)"""

    def get_progress(self, challenge_id: str) -> UserChallengeProgress | None:
        """Get user's progress for a specific challenge"""

        return (
            self.db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == self.namespace,
                UserChallengeProgress.user_id == self.session_context.user_id,
                UserChallengeProgress.challenge_id == challenge_id,
            )
            .first()
        )

    def get_or_create_progress(self, challenge_id: str) -> UserChallengeProgress:
        """Get or create user's progress for a challenge"""
        progress = self.get_progress(challenge_id)
        if not progress:
            progress = UserChallengeProgress(
                namespace=self.namespace,
                user_id=self.session_context.user_id,
                challenge_id=challenge_id,
                status="available",
            )
            self.db.add(progress)
            self.db.flush()
        return progress

    def get_all_progress(self) -> list[UserChallengeProgress]:
        """Get all challenge progress for user"""
        return (
            self.db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == self.namespace,
                UserChallengeProgress.user_id == self.session_context.user_id,
            )
            .all()
        )

    def get_progress_map(self) -> dict[str, str]:
        """Get challenge_id -> status mapping for user"""
        progress_list = self.get_all_progress()
        return {p.challenge_id: p.status for p in progress_list}

    def get_completed_challenges(self) -> list[UserChallengeProgress]:
        """Get completed challenges for user"""
        return (
            self.db.query(UserChallengeProgress)
            .filter(
                UserChallengeProgress.namespace == self.namespace,
                UserChallengeProgress.user_id == self.session_context.user_id,
                UserChallengeProgress.status == "completed",
            )
            .all()
        )

    def use_hint(self, challenge_id: str, hint_cost: int) -> UserChallengeProgress:
        """Use a hint for a challenge"""
        progress = self.get_or_create_progress(challenge_id)
        progress.hints_used += 1
        progress.hints_cost += hint_cost
        if progress.status == "available":
            progress.status = "in_progress"

        self.db.commit()

        return progress

    def record_attempt(self, challenge_id: str) -> UserChallengeProgress:
        """Record an attempt on a challenge"""
        progress = self.get_or_create_progress(challenge_id)
        progress.attempts += 1
        if progress.first_attempt_at is None:
            progress.first_attempt_at = datetime.now(UTC)
        if progress.status == "available":
            progress.status = "in_progress"
        self.db.commit()
        return progress

    def mark_completed(
        self,
        challenge_id: str,
        evidence: dict,
        workflow_id: str | None = None,
    ) -> UserChallengeProgress:
        """Mark challenge as completed"""
        progress = self.get_or_create_progress(challenge_id)

        now = datetime.now(UTC)
        progress.status = "completed"
        progress.successful_attempts += 1
        progress.completed_at = now

        if progress.first_attempt_at:
            progress.completion_time_seconds = int(
                (now - progress.first_attempt_at).total_seconds()
            )

        progress.completion_evidence = json.dumps(evidence)
        progress.completion_workflow_id = workflow_id

        self.db.commit()

        return progress

    def get_stats(self) -> dict:
        """Get challenge statistics for user"""
        all_progress = self.get_all_progress()

        completed = [p for p in all_progress if p.status == "completed"]
        in_progress = [p for p in all_progress if p.status == "in_progress"]

        return {
            "completed_count": len(completed),
            "completed_ids": [p.challenge_id for p in completed],
            "in_progress_count": len(in_progress),
            "total_attempts": sum(p.attempts for p in all_progress),
            "hints_used": sum(p.hints_used for p in all_progress),
            "hints_cost": sum(p.hints_cost for p in all_progress),
        }


# =============================================================================
# Badge Repository
# =============================================================================


class BadgeRepository:
    """Repository for Badge definitions (global, not namespaced)"""

    def __init__(self, db: Session):
        self.db = db

    def list_badges(
        self,
        category: str | None = None,
        active_only: bool = True,
        include_secret: bool = False,
    ) -> list[Badge]:
        """List badges with optional filters"""

        query = self.db.query(Badge)

        if active_only:
            query = query.filter(Badge.is_active == True)
        if not include_secret:
            query = query.filter(Badge.is_secret == False)
        if category:
            query = query.filter(Badge.category == category)

        rarity_order = case(
            {"legendary": 0, "epic": 1, "rare": 2, "common": 3},
            value=Badge.rarity,
            else_=4,
        )
        return query.order_by(rarity_order, Badge.id).all()

    def get_badge(self, badge_id: str) -> Badge | None:
        """Get badge by ID"""
        return self.db.query(Badge).filter(Badge.id == badge_id).first()

    def count_badges(self, include_secret: bool = False) -> int:
        """Count active badges"""
        query = self.db.query(Badge).filter(Badge.is_active == True)
        if not include_secret:
            query = query.filter(Badge.is_secret == False)
        return query.count()

    def get_total_points(self, badge_ids: list[str]) -> int:
        """Get total points for given badge IDs"""
        if not badge_ids:
            return 0
        return (
            self.db.query(func.sum(Badge.points))
            .filter(Badge.id.in_(badge_ids))
            .scalar()
            or 0
        )


# =============================================================================
# User Badge Repository
# =============================================================================


class UserBadgeRepository(NamespacedRepository):
    """Repository for user badges (namespaced)"""

    def get_earned_badges(self) -> list[UserBadge]:
        """Get all badges earned by user"""
        return (
            self.db.query(UserBadge)
            .filter(
                UserBadge.namespace == self.namespace,
                UserBadge.user_id == self.session_context.user_id,
            )
            .order_by(UserBadge.earned_at.desc())
            .all()
        )

    def get_earned_badge_ids(self) -> set[str]:
        """Get set of earned badge IDs"""
        badges = self.get_earned_badges()
        return {b.badge_id for b in badges}

    def has_badge(self, badge_id: str) -> bool:
        """Check if user has earned a specific badge"""
        return (
            self.db.query(UserBadge)
            .filter(
                UserBadge.namespace == self.namespace,
                UserBadge.user_id == self.session_context.user_id,
                UserBadge.badge_id == badge_id,
            )
            .first()
            is not None
        )

    def get_user_badge(self, badge_id: str) -> "UserBadge | None":
        """Get specific user badge"""
        return (
            self.db.query(UserBadge)
            .filter(
                UserBadge.namespace == self.namespace,
                UserBadge.user_id == self.session_context.user_id,
                UserBadge.badge_id == badge_id,
            )
            .first()
        )

    def award_badge(
        self,
        badge_id: str,
        context: dict,
        workflow_id: str | None = None,
    ) -> "UserBadge":
        """Award badge to user (idempotent)"""
        existing = self.get_user_badge(badge_id)
        if existing:
            return existing

        user_badge = UserBadge(
            namespace=self.namespace,
            user_id=self.session_context.user_id,
            badge_id=badge_id,
            earned_at=datetime.now(UTC),
            earning_context=json.dumps(context),
            earning_workflow_id=workflow_id,
        )
        self.db.add(user_badge)
        self.db.commit()

        return user_badge

    def count_earned(self) -> int:
        """Count badges earned by user"""
        return (
            self.db.query(UserBadge)
            .filter(
                UserBadge.namespace == self.namespace,
                UserBadge.user_id == self.session_context.user_id,
            )
            .count()
        )


# =============================================================================
# CTF Event Repository
# =============================================================================


class CTFEventRepository(NamespacedRepository):
    """Repository for CTF activity events (namespaced)"""

    def get_events(
        self,
        limit: int = 50,
        offset: int = 0,
        category: str | None = None,
        workflow_id: str | None = None,
        vendor_id: int | None = None,
    ) -> list[CTFEvent]:
        """Get paginated activity events"""
        query = self.db.query(CTFEvent).filter(
            CTFEvent.namespace == self.namespace,
            CTFEvent.user_id == self.session_context.user_id,
        )

        if category:
            query = query.filter(CTFEvent.event_category == category)
        if workflow_id:
            query = query.filter(CTFEvent.workflow_id == workflow_id)
        if vendor_id:
            query = query.filter(CTFEvent.vendor_id == vendor_id)

        return (
            query.order_by(CTFEvent.timestamp.desc()).offset(offset).limit(limit).all()
        )

    def count_events(
        self,
        category: str | None = None,
        workflow_id: str | None = None,
        vendor_id: int | None = None,
    ) -> int:
        """Count events with filters"""
        query = self.db.query(CTFEvent).filter(
            CTFEvent.namespace == self.namespace,
            CTFEvent.user_id == self.session_context.user_id,
        )

        if category:
            query = query.filter(CTFEvent.event_category == category)
        if workflow_id:
            query = query.filter(CTFEvent.workflow_id == workflow_id)
        if vendor_id:
            query = query.filter(CTFEvent.vendor_id == vendor_id)

        return query.count()

    def get_workflow_events(self, workflow_id: str) -> list[CTFEvent]:
        """Get all events for a specific workflow"""
        return (
            self.db.query(CTFEvent)
            .filter(
                CTFEvent.namespace == self.namespace,
                CTFEvent.workflow_id == workflow_id,
            )
            .order_by(CTFEvent.timestamp)
            .all()
        )

    # -- Exfil data (tool-based captures for Hacker Toolkit) --

    EXFIL_TOOL_NAMES = {"network_request"}

    def get_exfil_events(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CTFEvent]:
        """Get network_request tool call events (exfil captures)."""
        return (
            self.db.query(CTFEvent)
            .filter(
                CTFEvent.namespace == self.namespace,
                CTFEvent.user_id == self.session_context.user_id,
                CTFEvent.tool_name.in_(self.EXFIL_TOOL_NAMES),
            )
            .order_by(CTFEvent.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_exfil_events(self) -> int:
        """Count exfil-relevant tool call events."""
        return (
            self.db.query(CTFEvent)
            .filter(
                CTFEvent.namespace == self.namespace,
                CTFEvent.user_id == self.session_context.user_id,
                CTFEvent.tool_name.in_(self.EXFIL_TOOL_NAMES),
            )
            .count()
        )


# =============================================================================
# SSRF Validation
# =============================================================================

# Ranges that must never be reachable via user-supplied webhook URLs.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_webhook_url(url: str) -> tuple[bool, str | None]:
    """Validate a webhook URL for safety.

    In DEBUG mode, localhost and private IPs are allowed so developers
    can test webhooks against local servers. In production, these are
    blocked to prevent SSRF.

    Returns (is_valid, error_message).
    """
    from finbot.config import settings  # pylint: disable=import-outside-toplevel

    if not url:
        return False, "Webhook URL is required"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ("https", "http"):
        return False, "URL scheme must be https (or http for development)"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a hostname"

    if hostname == "metadata.google.internal":
        return False, f"Hostname '{hostname}' is not allowed"

    if not settings.DEBUG:
        if hostname == "localhost":
            return False, f"Hostname '{hostname}' is not allowed"

        try:
            addr = ipaddress.ip_address(hostname)
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False, f"IP address {hostname} is in a blocked range"
        except ValueError:
            pass

    if not parsed.port and parsed.scheme == "https":
        pass
    elif parsed.port and parsed.port in (80, 443):
        pass
    elif parsed.port and not (1024 <= parsed.port <= 65535):
        return False, f"Port {parsed.port} is not in the allowed range (1024-65535)"

    return True, None


# =============================================================================
# Labs Guardrail Config Repository
# =============================================================================


class LabsGuardrailConfigRepository(NamespacedRepository):
    """Repository for LabsGuardrailConfig — one config per (namespace, user_id)."""

    VALID_HOOK_KINDS = frozenset(
        {
            "before_model",
            "after_model",
            "before_tool",
            "after_tool",
        }
    )

    def get_for_current_user(self) -> LabsGuardrailConfig | None:
        return (
            self._add_namespace_filter(
                self.db.query(LabsGuardrailConfig), LabsGuardrailConfig
            )
            .filter(
                LabsGuardrailConfig.user_id == self.session_context.user_id,
            )
            .first()
        )

    def upsert(
        self,
        webhook_url: str,
        hooks: dict[str, bool] | None = None,
        timeout_seconds: int = 5,
        enabled: bool = True,
    ) -> tuple[LabsGuardrailConfig, bool]:
        """Create or update guardrail config for the current user.

        Returns (config, created) where created=True if a new row was inserted.
        """
        valid, err = validate_webhook_url(webhook_url)
        if not valid:
            raise ValueError(err)

        if hooks is not None:
            unknown = set(hooks.keys()) - self.VALID_HOOK_KINDS
            if unknown:
                raise ValueError(f"Unknown hook kinds: {', '.join(sorted(unknown))}")
        else:
            hooks = {k: True for k in self.VALID_HOOK_KINDS}

        timeout_seconds = max(1, min(timeout_seconds, 30))

        existing = self.get_for_current_user()
        if existing:
            existing.webhook_url = webhook_url
            existing.hooks_json = json.dumps(hooks)
            existing.timeout_seconds = timeout_seconds
            existing.enabled = enabled
            existing.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(existing)
            return existing, False

        signing_secret = secrets.token_urlsafe(32)
        config = LabsGuardrailConfig(
            namespace=self.namespace,
            user_id=self.session_context.user_id,
            webhook_url=webhook_url,
            signing_secret=signing_secret,
            enabled=enabled,
            hooks_json=json.dumps(hooks),
            timeout_seconds=timeout_seconds,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config, True

    def toggle_enabled(self) -> LabsGuardrailConfig | None:
        config = self.get_for_current_user()
        if config:
            config.enabled = not config.enabled
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config

    def rotate_secret(self) -> LabsGuardrailConfig | None:
        config = self.get_for_current_user()
        if config:
            config.signing_secret = secrets.token_urlsafe(32)
            config.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(config)
        return config

    def delete_config(self) -> bool:
        config = self.get_for_current_user()
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True
