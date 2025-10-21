"""Session management for FinBot CTF Platform"""

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from finbot.config import settings
from finbot.core.data.database import SessionLocal
from finbot.core.data.models import User, UserSession
from finbot.core.utils import create_fingerprint_data

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """
    Session context for authentication and authorization with namespace isolation.
    """

    session_id: str
    user_id: str
    is_temporary: bool
    namespace: str
    created_at: datetime
    expires_at: datetime
    email: str | None = None
    user_agent: str | None = None

    # security fields
    last_rotation: datetime = field(default_factory=lambda: datetime.now(UTC))
    rotation_count: int = 0
    strict_fingerprint: str = ""
    loose_fingerprint: str = ""
    original_ip: str = ""
    current_ip: str = ""
    needs_cookie_update: bool = False
    was_rotated: bool = False
    security_event: str | None = None
    csrf_token: str = ""

    # Vendor Context
    current_vendor_id: int | None = None
    current_vendor: dict | None = None
    available_vendors: list[dict] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Check if session is valid"""
        if isinstance(self.expires_at, str):
            expires_at = datetime.fromisoformat(self.expires_at)
        else:
            expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) < expires_at

    def should_rotate(self) -> bool:
        """Check if session should be rotated"""
        if not settings.ENABLE_SESSION_ROTATION:
            return False
        # Permanent sessions (email bound) are rotated more frequently for added security.
        rotation_interval = (
            settings.TEMP_SESSION_ROTATION_INTERVAL
            if self.is_temporary
            else settings.PERM_SESSION_ROTATION_INTERVAL
        )
        if self.last_rotation.tzinfo is None:
            self.last_rotation = self.last_rotation.replace(tzinfo=UTC)
        time_since_rotation = datetime.now(UTC) - self.last_rotation
        return time_since_rotation.total_seconds() > rotation_interval

    def is_too_old(self) -> bool:
        """Check if session is too old for a replacement - forced"""
        max_age = (
            settings.MAX_TEMP_SESSION_AGE
            if self.is_temporary
            else settings.MAX_PERM_SESSION_AGE
        )
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        session_age = datetime.now(UTC) - self.created_at
        return session_age.total_seconds() > max_age

    def detect_suspicious_activity(self) -> bool:
        """Detect suspicious activity
        - Some basic protection - not fool proof by any means.
        """
        if not settings.ENABLE_HIJACK_DETECTION:
            return False
        # detection: check for too many recent rotations
        if self.rotation_count >= settings.SUSPICIOUS_ROTATION_THRESHOLD:
            avg_rotation_interval = (
                datetime.now(UTC) - self.created_at
            ).total_seconds() / max(1, self.rotation_count)
            min_expected_interval = (
                settings.TEMP_SESSION_ROTATION_INTERVAL
                if self.is_temporary
                else settings.PERM_SESSION_ROTATION_INTERVAL
            )
            if avg_rotation_interval < min_expected_interval * 0.8:
                return True
        return False

    def get_security_status(self) -> dict:
        """Get security status for monitoring"""
        return {
            "rotation_count": self.rotation_count,
            "time_since_rotation": (
                datetime.now(UTC) - self.last_rotation
            ).total_seconds(),
            "session_age": (datetime.now(UTC) - self.created_at).total_seconds(),
            "should_rotate": self.should_rotate(),
            "is_too_old": self.is_too_old(),
            "suspicious_activity": self.detect_suspicious_activity(),
            "fingerprint_protected": bool(
                self.strict_fingerprint or self.loose_fingerprint
            ),
        }

    def has_vendor_context(self) -> bool:
        """Check if user has vendor context"""
        return self.current_vendor_id is not None

    def is_multi_vendor_user(self) -> bool:
        """Check if user has multiple vendors"""
        return len(self.available_vendors) > 1

    def requires_vendor_selection(self) -> bool:
        """Check if user needs to select a vendor"""
        return len(self.available_vendors) > 0 and not self.has_vendor_context()

    def get_vendor_display_name(self) -> str:
        """Get display name for current vendor"""
        if self.current_vendor:
            return self.current_vendor.get("company_name", "Unknown Vendor")
        return "No Vendor Selected"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "email": self.email,
            "is_temporary": self.is_temporary,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "last_rotation": self.last_rotation.isoformat().replace("+00:00", "Z"),
            "rotation_count": self.rotation_count,
            "strict_fingerprint": self.strict_fingerprint,
            "loose_fingerprint": self.loose_fingerprint,
            "csrf_token": self.csrf_token,
            "original_ip": self.original_ip,
        }


class SessionManager:
    """Session manager for FinBot CTF Platform"""

    def __init__(self):
        self.signing_key = settings.SESSION_SIGNING_KEY.encode()
        self.namespace_prefix = settings.NAMESPACE_PREFIX

    def create_session(
        self,
        email: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        accept_language: str | None = None,
        accept_encoding: str | None = None,
    ) -> SessionContext:
        """Create a new session for a user with namespace isolation

        Args:
            email: Optional email for persistent session
            user_agent: User agent of the browser
            ip_address: Client IP address
            accept_language: Accept-Language header from request
            accept_encoding: Accept-Encoding header from request

        Returns:
            SessionContext: Session context for the user with isolation
        """
        # generate session id - cryptographically secure
        session_id = secrets.token_urlsafe(32)

        if email:
            user_id = hashlib.sha256(
                f"{email}:{settings.SECRET_KEY}".encode()
            ).hexdigest()[:16]
            is_temporary = False
        else:
            user_id = f"temp_{secrets.token_urlsafe(12)}"
            is_temporary = True

        namespace = f"{self.namespace_prefix}{user_id}"

        # compute expiry
        now = datetime.now(UTC)
        session_lifetime = (
            settings.TEMP_SESSION_TIMEOUT
            if is_temporary
            else settings.PERM_SESSION_TIMEOUT
        )
        expires_at = now + timedelta(seconds=session_lifetime)

        # Create tiered fingerprints for enhanced security with stability
        strict_fingerprint_data = create_fingerprint_data(
            user_agent, accept_language, accept_encoding, "strict"
        )
        loose_fingerprint_data = create_fingerprint_data(
            user_agent, accept_language, accept_encoding, "loose"
        )

        # create session context
        session_context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            email=email,
            is_temporary=is_temporary,
            namespace=namespace,
            created_at=now,
            expires_at=expires_at,
            strict_fingerprint=hashlib.sha256(
                strict_fingerprint_data.encode()
            ).hexdigest()[:16],
            loose_fingerprint=hashlib.sha256(
                loose_fingerprint_data.encode()
            ).hexdigest()[:16],
            original_ip=ip_address or "",
            current_ip=ip_address or "",
            user_agent=user_agent,
            csrf_token=secrets.token_urlsafe(32),
            needs_cookie_update=True,
        )
        # store in db with integrity protection
        self._store_session_securely(session_context)

        return session_context

    def _store_session_securely(self, session_context: SessionContext):
        """Store session in db with integrity protection - HMAC signatures"""
        db = SessionLocal()
        try:
            if session_context.email:
                user = (
                    db.query(User)
                    .filter(User.user_id == session_context.user_id)
                    .first()
                )
                if not user:
                    # later: we can create fun display names
                    user = User(
                        user_id=session_context.user_id,
                        namespace=session_context.namespace,
                        email=session_context.email,
                        display_name=session_context.email.split("@")[0],
                    )
                    db.add(user)
                else:
                    user.last_login = session_context.created_at

            # prepare session data
            session_data = session_context.to_dict()
            session_data_json = json.dumps(session_data, sort_keys=True)
            signature = self._sign_session_data(session_data_json)

            session = UserSession(
                session_id=session_context.session_id,
                user_id=session_context.user_id,
                email=session_context.email,
                is_temporary=session_context.is_temporary,
                namespace=session_context.namespace,
                session_data=session_data_json,
                signature=signature,
                created_at=session_context.created_at,
                last_accessed=session_context.created_at,
                expires_at=session_context.expires_at,
                user_agent=session_context.user_agent,
                last_rotation=session_context.last_rotation,
                rotation_count=session_context.rotation_count,
                original_ip=session_context.original_ip,
                current_ip=session_context.current_ip,
                strict_fingerprint=session_context.strict_fingerprint,
                loose_fingerprint=session_context.loose_fingerprint,
            )
            db.add(session)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                "Failed to store session for user %s: %s", session_context.user_id, e
            )
            raise RuntimeError(f"Failed to store session: {e}") from e
        finally:
            db.close()

    def _sign_session_data(self, session_data: str) -> str:
        """Create HMAC signature for session data"""
        return hmac.new(
            self.signing_key, session_data.encode(), hashlib.sha256
        ).hexdigest()

    def _verify_session_signature(self, session_data: str, signature: str) -> bool:
        """Verify session data integrity using HMAC"""
        expected_signature = self._sign_session_data(session_data)
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, signature)

    def get_session(
        self,
        session_id: str,
        current_strict_fingerprint: str = "",
        current_loose_fingerprint: str = "",
        current_ip: str = "",
    ) -> tuple[SessionContext | None, str]:
        """Retrieve and validate session with tiered security validation and rotation

        Args:
            session_id: Session ID
            current_strict_fingerprint: Strict fingerprint (stable fields only)
            current_loose_fingerprint: Loose fingerprint (includes normalized user_agent)
            current_ip: Current client IP address (used for monitoring, not strict validation)

        Returns:
            tuple[SessionContext | None, str]: Session context for the user
            with isolation if valid else None and security status message
        """
        db = SessionLocal()
        try:
            session = (
                db.query(UserSession)
                .filter(UserSession.session_id == session_id)
                .first()
            )
            if not session:
                return None, "session_not_found"

            if session.is_expired():
                # clean up expire session
                db.delete(session)
                db.commit()
                return None, "session_expired"

            # verify signature
            if not self._verify_session_signature(
                session.session_data, session.signature
            ):
                db.delete(session)
                db.commit()
                return None, "session_tampered"

            session_data = json.loads(session.session_data)
            csrf_token = session_data.get("csrf_token")

            # Handle missing CSRF token (should not happen in normal operation)
            if not csrf_token:
                logger.warning(
                    "Missing CSRF token for session %s, generating new one",
                    session_id[:8],
                )
                csrf_token = secrets.token_urlsafe(32)
                # Update session data with new CSRF token
                session_data["csrf_token"] = csrf_token
                session.session_data = json.dumps(session_data, sort_keys=True)
                session.signature = self._sign_session_data(session.session_data)

            session_context = SessionContext(
                session_id=session.session_id,
                user_id=session.user_id,
                email=session.email,
                is_temporary=session.is_temporary,
                namespace=session.namespace,
                created_at=session.created_at,
                expires_at=session.expires_at,
                user_agent=session.user_agent,
                last_rotation=session.last_rotation or datetime.now(UTC),
                rotation_count=session.rotation_count or 0,
                strict_fingerprint=session.strict_fingerprint or "",
                loose_fingerprint=session.loose_fingerprint or "",
                original_ip=session.original_ip or "",
                current_ip=current_ip,  # Set from current request
                csrf_token=csrf_token,
                needs_cookie_update=False,
                was_rotated=False,
                security_event=None,
            )

            # IP address monitoring (logging only, not strict validation)
            if current_ip and session_context.original_ip:
                if current_ip != session_context.original_ip:
                    logger.info(
                        "IP change detected for session %s: %s -> %s",
                        session_id[:8],
                        session_context.original_ip,
                        current_ip,
                    )

            # Tiered fingerprint validation
            if settings.ENABLE_FINGERPRINT_VALIDATION:
                fingerprint_valid = False
                validation_method = "none"

                # Try strict fingerprint first (most stable)
                if (
                    current_strict_fingerprint
                    and session_context.strict_fingerprint
                    and session_context.strict_fingerprint == current_strict_fingerprint
                ):
                    fingerprint_valid = True
                    validation_method = "strict"
                # Fallback to loose fingerprint (includes normalized user_agent)
                elif (
                    current_loose_fingerprint
                    and session_context.loose_fingerprint
                    and session_context.loose_fingerprint == current_loose_fingerprint
                ):
                    fingerprint_valid = True
                    validation_method = "loose"

                # Handle fingerprint validation failure
                if not fingerprint_valid and (
                    current_strict_fingerprint or current_loose_fingerprint
                ):
                    if session_context.is_temporary:
                        # Strict validation for temporary sessions
                        db.delete(session)
                        db.commit()
                        logger.warning(
                            "Fingerprint validation failed for temporary session %s",
                            session_id[:8],
                        )
                        return None, "session_hijacked"
                    else:
                        # Lenient handling for permanent sessions
                        session_context.security_event = (
                            f"fingerprint_mismatch_{validation_method}"
                        )
                        session_context.needs_cookie_update = True
                        logger.warning(
                            "Fingerprint mismatch for permanent session %s (method: %s)",
                            session_id[:8],
                            validation_method,
                        )
                else:
                    logger.debug(
                        "Fingerprint validation successful for session %s (method: %s)",
                        session_id[:8],
                        validation_method,
                    )

            # check if session is too old
            if session_context.is_too_old():
                db.delete(session)
                db.commit()
                return None, "session_too_old"

            # check for rotation
            if session_context.should_rotate():
                rotated_context = self._rotate_session(session_context, db)
                return rotated_context, "session_rotated"

            session.last_accessed = datetime.now(UTC)
            db.commit()

            return session_context, "session_valid"
        finally:
            db.close()

    def _rotate_session(
        self, old_context: SessionContext, db: Session
    ) -> SessionContext:
        """Rotate session ID while preserving user context
        - Preserves namespace and user context
        """
        new_session_id = secrets.token_urlsafe(32)

        new_context = SessionContext(
            session_id=new_session_id,
            user_id=old_context.user_id,
            email=old_context.email,
            is_temporary=old_context.is_temporary,
            namespace=old_context.namespace,
            created_at=old_context.created_at,
            expires_at=old_context.expires_at,
            last_rotation=datetime.now(UTC),
            rotation_count=old_context.rotation_count + 1,
            strict_fingerprint=old_context.strict_fingerprint,
            loose_fingerprint=old_context.loose_fingerprint,
            original_ip=old_context.original_ip,
            current_ip=old_context.current_ip,
            user_agent=old_context.user_agent,
            csrf_token=old_context.csrf_token,
            needs_cookie_update=True,
            was_rotated=True,
        )
        self._store_session_securely(new_context)

        # delete old session
        old_session = (
            db.query(UserSession)
            .filter(UserSession.session_id == old_context.session_id)
            .first()
        )
        if old_session:
            db.delete(old_session)

        db.commit()
        return new_context

    def delete_session(self, session_id: str) -> bool:
        """Delete session by session id"""
        db = SessionLocal()
        try:
            session = (
                db.query(UserSession)
                .filter(UserSession.session_id == session_id)
                .first()
            )
            if session:
                db.delete(session)
                db.commit()
                return True
            return False
        finally:
            db.close()

    def cleanup_expired_sessions(self) -> int:
        """Cleanup expired sessions"""
        db = SessionLocal()
        try:
            expired_sessions = (
                db.query(UserSession)
                .filter(UserSession.expires_at < datetime.now(UTC))
                .all()
            )
            for session in expired_sessions:
                db.delete(session)
            db.commit()
            return len(expired_sessions)
        finally:
            db.close()

    # Vendor Context Management
    def update_vendor_context(self, session_id: str, vendor_id: int | None) -> bool:
        """Update current vendor for ALL user sessions (global sync)"""
        db = SessionLocal()
        try:
            # Get the session to find the user
            session = (
                db.query(UserSession)
                .filter(UserSession.session_id == session_id)
                .first()
            )

            if not session:
                return False

            # Update ALL sessions for this user (global sync)
            updated_count = (
                db.query(UserSession)
                .filter(UserSession.user_id == session.user_id)
                .update({"current_vendor_id": vendor_id})
            )

            db.commit()

            logger.info(
                "Updated vendor context for user %s: vendor_id=%s, sessions_updated=%d",
                session.user_id[:8],
                vendor_id,
                updated_count,
            )
            return updated_count > 0
        finally:
            db.close()

    def get_session_with_vendor_context(
        self, session_id: str, **kwargs
    ) -> tuple[SessionContext | None, str]:
        """Get session with vendor context loaded"""
        session_context, status = self.get_session(session_id, **kwargs)

        if session_context:
            session_context = self.load_vendor_context(session_context)

        return session_context, status

    def load_vendor_context(self, session_context: SessionContext) -> SessionContext:
        """Load vendor context from database"""
        db = SessionLocal()
        try:
            # Get user's current vendor from session
            session = (
                db.query(UserSession)
                .filter(UserSession.session_id == session_context.session_id)
                .first()
            )

            current_vendor_id = session.current_vendor_id if session else None

            # Get all available vendors for user
            # avoid circular import; pylint: disable=import-outside-toplevel
            from finbot.core.data.repositories import VendorRepository

            vendor_repo = VendorRepository(db, session_context)
            vendors = vendor_repo.list_vendors() or []

            available_vendors = [
                {
                    "id": v.id,
                    "company_name": v.company_name,
                    "vendor_category": v.vendor_category,
                    "industry": v.industry,
                    "status": v.status,
                    "created_at": v.created_at.isoformat().replace("+00:00", "Z"),
                }
                for v in vendors
            ]

            # If no current vendor set but vendors exist, set first as default
            if not current_vendor_id and available_vendors:
                current_vendor_id = available_vendors[0]["id"]
                # Update session with default
                if session:
                    session.current_vendor_id = current_vendor_id
                    db.commit()
                    logger.info(
                        "Set default vendor for user %s: vendor_id=%s",
                        session_context.user_id[:8],
                        current_vendor_id,
                    )

            # Find current vendor details
            current_vendor = None
            if current_vendor_id:
                current_vendor = next(
                    (v for v in available_vendors if v["id"] == current_vendor_id), None
                )

            # Update session context
            session_context.current_vendor_id = current_vendor_id
            session_context.current_vendor = current_vendor
            session_context.available_vendors = available_vendors

            return session_context
        finally:
            db.close()


# Global session manager instance
session_manager = SessionManager()
