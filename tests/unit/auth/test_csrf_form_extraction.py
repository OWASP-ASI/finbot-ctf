"""Tests for CSRF token extraction from form submissions.

Covers:
- Issue #200: CSRF protection silently skipped for form submissions
"""

import pytest
from unittest.mock import MagicMock

from finbot.core.auth.csrf import CSRFProtectionMiddleware
from finbot.config import settings


@pytest.fixture
def csrf_middleware():
    app = MagicMock()
    return CSRFProtectionMiddleware(app)


def _make_request(headers=None, form_data=None):
    """Create a mock request with given headers and form data."""
    request = MagicMock()
    request.headers = headers or {}

    async def mock_form():
        return form_data or {}

    request.form = mock_form
    return request


class TestExtractCsrfToken:
    """Tests for _extract_csrf_token."""

    @pytest.mark.asyncio
    async def test_extracts_token_from_header(self, csrf_middleware):
        """Header-based CSRF should still work."""
        request = _make_request(
            headers={settings.CSRF_HEADER_NAME: "test-token-123"}
        )
        token = await csrf_middleware._extract_csrf_token(request)
        assert token == "test-token-123"

    @pytest.mark.asyncio
    async def test_extracts_token_from_form_urlencoded(self, csrf_middleware):
        """Form submissions should extract CSRF token from form body."""
        request = _make_request(
            headers={"content-type": "application/x-www-form-urlencoded"},
            form_data={settings.CSRF_TOKEN_NAME: "form-token-456"},
        )
        token = await csrf_middleware._extract_csrf_token(request)
        assert token == "form-token-456"

    @pytest.mark.asyncio
    async def test_extracts_token_from_multipart_form(self, csrf_middleware):
        """Multipart form submissions should extract CSRF token."""
        request = _make_request(
            headers={"content-type": "multipart/form-data; boundary=---"},
            form_data={settings.CSRF_TOKEN_NAME: "multipart-token-789"},
        )
        token = await csrf_middleware._extract_csrf_token(request)
        assert token == "multipart-token-789"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token_in_form(self, csrf_middleware):
        """Form without CSRF token should return None."""
        request = _make_request(
            headers={"content-type": "application/x-www-form-urlencoded"},
            form_data={"other_field": "value"},
        )
        token = await csrf_middleware._extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_header_takes_priority_over_form(self, csrf_middleware):
        """Header token should be returned even if form also has a token."""
        request = _make_request(
            headers={
                settings.CSRF_HEADER_NAME: "header-token",
                "content-type": "application/x-www-form-urlencoded",
            },
            form_data={settings.CSRF_TOKEN_NAME: "form-token"},
        )
        token = await csrf_middleware._extract_csrf_token(request)
        assert token == "header-token"
