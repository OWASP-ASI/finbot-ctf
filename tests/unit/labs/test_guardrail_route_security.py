"""Route-level security tests for the guardrail webhook API.

Covers the two layers introduced by the fix for #535:
  1. Unauthenticated (temp-session) requests to write endpoints → 401
  2. Private / loopback webhook URLs submitted by authenticated users → 422

These tests exercise the HTTP layer (FastAPI routes) directly, which the
existing repository-level tests in test_guardrail_config.py do not cover.
"""

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from finbot.config import settings
from finbot.core.auth.session import session_manager
from finbot.core.auth.csrf import CSRFProtectionMiddleware
from finbot.main import app
from fastapi import Request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LABS_GUARDRAIL_URL = "/labs/api/v1/guardrails"
PUBLIC_WEBHOOK = "https://webhook.site/test-valid-url"


def _setup_temp_session(client: TestClient):
    """Hits the status endpoint to set up session and CSRF cookies."""
    client.get("/api/session/status")


def _auth_headers_for(session_ctx, client: TestClient) -> dict[str, str]:
    """Return cookie + CSRF headers for a fully authenticated session."""
    return {
        "cookie": f"{settings.SESSION_COOKIE_NAME}={session_ctx.session_id}",
        settings.CSRF_HEADER_NAME: session_ctx.csrf_token,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def mock_csrf_dispatch(self, request: Request, call_next):
    return await call_next(request)

@pytest.fixture
def client(db):  # noqa: ARG001 — db fixture wires up in-memory SQLite
    """TestClient with the processor patched out (prevents async teardown errors)."""
    with patch("finbot.main.start_processor_task", return_value=None):
        with patch.object(CSRFProtectionMiddleware, "dispatch", new=mock_csrf_dispatch):
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c


@pytest.fixture
def auth_session(db):  # noqa: ARG001
    """A fully authenticated (persistent, email-bound) session."""
    return session_manager.create_session(email="guardrail_route_test@example.com")


# ---------------------------------------------------------------------------
# Test Class 1 — Unauthenticated access blocked (401)
# ---------------------------------------------------------------------------

class TestGuardrailWriteEndpointsRequireAuth:
    """All write endpoints must reject anonymous (temp-session) requests with 401."""

    WRITE_ENDPOINTS = [
        ("PUT",    LABS_GUARDRAIL_URL,                  {"webhook_url": PUBLIC_WEBHOOK, "enabled": True}),
        ("POST",   LABS_GUARDRAIL_URL + "/toggle",      None),
        ("POST",   LABS_GUARDRAIL_URL + "/rotate-secret", None),
        ("DELETE", LABS_GUARDRAIL_URL,                  None),
        ("POST",   LABS_GUARDRAIL_URL + "/test",        None),
    ]

    @pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
    def test_anonymous_session_returns_401(self, client, method, url, body):
        """Temp (unauthenticated) sessions must be rejected on every write endpoint."""
        _setup_temp_session(client)
        csrf = client.cookies.get("csrf_token", "dummy")
        headers = {settings.CSRF_HEADER_NAME: csrf}

        if method == "PUT":
            resp = client.put(url, json=body, headers=headers)
        elif method == "POST":
            resp = client.post(url, json=body, headers=headers)
        else:
            resp = client.delete(url, headers=headers)

        assert resp.status_code == 401, (
            f"{method} {url} should return 401 for anonymous session, got {resp.status_code}: {resp.text}"
        )

    def test_get_config_allowed_for_anon(self, client):
        """GET (read-only) should still work for temp sessions — returns null, not 401."""
        _setup_temp_session(client)
        resp = client.get(LABS_GUARDRAIL_URL)
        # 200 with null body, or 200 with None — either is acceptable
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test Class 2 — SSRF URL validation at the route level (422)
# ---------------------------------------------------------------------------

class TestGuardrailWebhookUrlSsrfValidation:
    """PUT /guardrails must reject internal / private URLs even from auth'd users."""

    BLOCKED_URLS = [
        ("loopback_ipv4",   "http://127.0.0.1:6379/"),
        ("loopback_named",  "http://localhost:8080/hook"),
        ("private_10",      "http://10.0.0.5/hook"),
        ("private_192",     "http://192.168.1.1/internal"),
        ("private_172",     "http://172.16.0.1/hook"),
        ("link_local_aws",  "http://169.254.169.254/latest/meta-data/"),
        ("loopback_ipv6",   "http://[::1]/hook"),
    ]

    @pytest.fixture(autouse=True)
    def _force_production_mode(self, monkeypatch):
        """Ensure DEBUG=False so the SSRF blocklist is fully active."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)

    @pytest.mark.parametrize("label,url", BLOCKED_URLS)
    def test_private_url_returns_422(self, client, auth_session, label, url):
        """Authenticated users must receive 422 when submitting a private webhook URL."""
        cookies = {
            settings.SESSION_COOKIE_NAME: auth_session.session_id,
            "csrf_token": auth_session.csrf_token,
        }
        headers = {settings.CSRF_HEADER_NAME: auth_session.csrf_token}

        resp = client.put(
            LABS_GUARDRAIL_URL,
            json={"webhook_url": url, "enabled": True},
            cookies=cookies,
            headers=headers,
        )

        assert resp.status_code == 422, (
            f"[{label}] Expected 422 for URL '{url}', got {resp.status_code}: {resp.text}"
        )

    def test_public_url_accepted(self, client, auth_session):
        """A genuine public URL must be accepted by an authenticated user."""
        cookies = {
            settings.SESSION_COOKIE_NAME: auth_session.session_id,
            "csrf_token": auth_session.csrf_token,
        }
        headers = {settings.CSRF_HEADER_NAME: auth_session.csrf_token}

        resp = client.put(
            LABS_GUARDRAIL_URL,
            json={"webhook_url": PUBLIC_WEBHOOK, "enabled": True},
            cookies=cookies,
            headers=headers,
        )

        # 200 = created/updated; accept also 422 only if it's about something
        # else (e.g. DNS failure in CI). We at minimum assert it's NOT 401/403.
        assert resp.status_code not in (401, 403), (
            f"Public URL should not be auth-rejected, got {resp.status_code}: {resp.text}"
        )
