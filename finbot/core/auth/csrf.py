"""CSRF Protection Middleware for FinBot CTF Platform"""

import hmac
import logging
from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from finbot.config import settings
from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF Protection Middleware

    Validates CSRF tokens for state-changing requests (POST, PUT, DELETE, PATCH)
    """

    # Methods that require CSRF protection
    PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    # Paths that are exempt from CSRF protection
    EXEMPT_PATHS = {
        "/api/health",
        "/api/status",
        "/static/",
        "/favicon.ico",
    }

    def __init__(self, app):
        super().__init__(app)
        self.enabled = settings.ENABLE_CSRF_PROTECTION

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Dispatch request with CSRF validation"""

        if not self.enabled:
            return await call_next(request)

        # Skip for safe methods (GET, HEAD, OPTIONS)
        if request.method not in self.PROTECTED_METHODS:
            return await call_next(request)

        # Skip for exempt paths
        if self._is_exempt_path(request.url.path):
            return await call_next(request)

        # Validate CSRF token
        try:
            self._validate_csrf_token(request)
        except HTTPException as e:
            logger.warning(
                "CSRF validation failed for %s %s from %s: %s",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
                e.detail,
            )
            # Handle CSRF error directly in middleware instead of letting it bubble up
            return self._create_csrf_error_response(request, e)

        # Process request
        response = await call_next(request)
        return response

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from CSRF protection"""
        return any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS)

    def _validate_csrf_token(self, request: Request) -> None:
        """Validate CSRF token from request"""

        # Get session context (should be set by SessionMiddleware)
        session_context: SessionContext | None = getattr(
            request.state, "session_context", None
        )
        if not session_context:
            raise HTTPException(
                status_code=403, detail="No session found - CSRF validation failed"
            )

        # Get expected CSRF token from session
        expected_token = session_context.csrf_token
        if not expected_token:
            raise HTTPException(status_code=403, detail="No CSRF token in session")

        # Get CSRF token from request
        request_token = self._extract_csrf_token(request)
        if not request_token:
            raise HTTPException(
                status_code=403, detail="CSRF token missing from request"
            )

        # Validate token
        if not self._compare_tokens(expected_token, request_token):
            raise HTTPException(status_code=403, detail="CSRF token mismatch")

        logger.debug(
            "CSRF validation successful for %s %s", request.method, request.url.path
        )

    def _extract_csrf_token(self, request: Request) -> str | None:
        """Extract CSRF token from request headers or form data"""

        # Try header first (for AJAX requests)
        token = request.headers.get(settings.CSRF_HEADER_NAME)
        if token:
            return token

        # Try form data (for regular form submissions)
        # Note: Form parsing in middleware is complex, so we primarily rely on header-based CSRF
        # Form-based CSRF tokens are handled by JavaScript submission or custom form parsing

        # For content-type application/x-www-form-urlencoded or multipart/form-data
        content_type = request.headers.get("content-type", "").lower()
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            # We'll need to parse form data, but this is tricky in middleware
            # For now, rely on header-based CSRF for API endpoints
            # Form-based CSRF will be handled by template injection
            pass

        return None

    def _compare_tokens(self, expected: str, actual: str) -> bool:
        """Securely compare CSRF tokens using constant-time comparison"""
        return hmac.compare_digest(expected, actual)

    def _create_csrf_error_response(
        self, request: Request, exc: HTTPException
    ) -> Response:
        """Create appropriate CSRF error response based on request type
        - Middleware error responses are not caught by FastAPI/Starlette default exception handlers
        - This is a workaround to handle CSRF errors in the middleware
        """

        # Check if this is an API request
        if self._is_api_request(request):
            return JSONResponse(
                content={
                    "error": {
                        "code": 403,
                        "message": "CSRF token validation failed",
                        "type": "csrf_error",
                        "details": exc.detail,
                    }
                },
                status_code=403,
            )
        else:
            # For web requests, show a dedicated CSRF error page
            try:
                with open(
                    "finbot/static/pages/error/403_csrf.html", "r", encoding="utf-8"
                ) as f:
                    content = f.read()
                return HTMLResponse(content=content, status_code=403)
            except FileNotFoundError:
                # Fallback if CSRF error page is missing
                return HTMLResponse(
                    content="<h1>403 Forbidden</h1><p>Security validation failed. Please refresh the page and try again.</p>",
                    status_code=403,
                )

    def _is_api_request(self, request: Request) -> bool:
        """Determine if the request is for an API endpoint"""
        return (
            request.url.path.startswith("/api/")
            or request.url.path.startswith("/vendor/api/")
            or "application/json" in request.headers.get("content-type", "")
            or "application/json" in request.headers.get("accept", "")
        )


def get_csrf_token(request: Request) -> str:
    """Helper function to get CSRF token for templates"""
    session_context: SessionContext | None = getattr(
        request.state, "session_context", None
    )
    if session_context and session_context.csrf_token:
        return session_context.csrf_token
    return ""


def csrf_token_field(request: Request) -> str:
    """Generate HTML hidden field with CSRF token"""
    token = get_csrf_token(request)
    if token:
        return (
            f'<input type="hidden" name="{settings.CSRF_TOKEN_NAME}" value="{token}">'
        )
    return ""


def csrf_token_meta(request: Request) -> str:
    """Generate HTML meta tag with CSRF token"""
    token = get_csrf_token(request)
    if token:
        return f'<meta name="csrf-token" content="{token}">'
    return ""
