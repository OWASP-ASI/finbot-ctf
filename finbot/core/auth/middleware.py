"""Enhanced middleware with automatic cookie enforcement"""

import hashlib
import logging

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from finbot.config import settings
from finbot.core.auth.session import (
    SessionContext,
    session_manager,
)
from finbot.core.utils import create_fingerprint_data

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseHTTPMiddleware):
    """Middleware that automatically handles session cookies and rotation"""

    async def dispatch(self, request: Request, call_next):
        """Dispatch request and handle session management"""
        session_context, status = await self._get_or_create_session(request)

        request.state.session_context = session_context
        request.state.session_status = status

        # Process request
        response = await call_next(request)

        if (
            session_context.needs_cookie_update
            or session_context.was_rotated
            or status in ["session_created", "session_rotated"]
        ):
            self._set_secure_session_cookie(response, session_context)

            if session_context.was_rotated:
                logger.info("🔄 Session rotated: %s", session_context.user_id)

        self._add_security_headers(response)

        return response

    async def _get_or_create_session(
        self, request: Request
    ) -> tuple[SessionContext, str]:
        """Get existing session or create new one with tiered security validation"""

        session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
        current_ip = request.client.host if request.client else ""

        # Create fingerprint types for validation
        user_agent = request.headers.get("User-Agent")
        accept_language = request.headers.get("Accept-Language")
        accept_encoding = request.headers.get("Accept-Encoding")

        current_strict_fingerprint = hashlib.sha256(
            create_fingerprint_data(
                user_agent, accept_language, accept_encoding, "strict"
            ).encode()
        ).hexdigest()[:16]
        current_loose_fingerprint = hashlib.sha256(
            create_fingerprint_data(
                user_agent, accept_language, accept_encoding, "loose"
            ).encode()
        ).hexdigest()[:16]

        if session_id:
            session_context, status = session_manager.get_session(
                session_id,
                current_strict_fingerprint,
                current_loose_fingerprint,
                current_ip,
            )

            if session_context:
                # ideally we should separate this and load only for vendor portal
                # but this info may be useful for other parts of the application
                session_context = session_manager.load_vendor_context(session_context)
                return session_context, status
            logger.warning("Session validation failed: %s", status)

        # Create new session with enhanced fingerprinting
        new_session = session_manager.create_session(
            user_agent=user_agent,
            ip_address=current_ip,
            accept_language=accept_language,
            accept_encoding=accept_encoding,
        )
        # load vendor context for new session
        new_session = session_manager.load_vendor_context(new_session)

        return new_session, "session_created"

    def _set_secure_session_cookie(
        self, response: Response, session_context: SessionContext
    ):
        """Automatically set secure session cookie"""

        max_age = (
            settings.TEMP_SESSION_TIMEOUT
            if session_context.is_temporary
            else settings.PERM_SESSION_TIMEOUT
        )

        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=session_context.session_id,
            max_age=max_age,
            httponly=settings.SESSION_COOKIE_HTTP_ONLY,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            path="/",
        )

    def _add_security_headers(self, response: Response):
        """Add security headers"""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"


# Dependencies for FastAPI routes
async def get_session_context(request: Request) -> SessionContext:
    """FastAPI dependency to get normal session context
    - This is used for routes that don't explicitly require authentication
    - May or may not be bound to an email address (temporary vs persistent)
    """
    return request.state.session_context


async def get_authenticated_session_context(request: Request) -> SessionContext:
    """FastAPI dependency to get authenticated session context
    - Requires a non-temporary session (bound to an email address aka persistent)
    - Raises 401 if the session is temporary
    """
    session_context = request.state.session_context

    if session_context.is_temporary:
        raise HTTPException(
            status_code=401,
            detail="Persistent session required. Please bind your email.",
        )

    return session_context
