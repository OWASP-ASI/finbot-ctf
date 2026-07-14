"""Route-level security tests for the darklab API.

Covers the fix for #544:
  1. Unauthenticated (temp-session) requests to supply-chain write endpoints → 401
  2. Authenticated requests → 200
  3. Read endpoints remain accessible to temp sessions → 200
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

DARKLAB_SUPPLY_CHAIN_TOOLS_URL = "/darklab/api/v1/supply-chain/servers/finmail/tools"
DARKLAB_SUPPLY_CHAIN_RESET_URL = "/darklab/api/v1/supply-chain/servers/finmail/reset-tools"


def _setup_temp_session(client: TestClient):
    """Hits the status endpoint to set up session and CSRF cookies."""
    client.get("/api/session/status")


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
    return session_manager.create_session(email="darklab_test@example.com")


# ---------------------------------------------------------------------------
# Test Class
# ---------------------------------------------------------------------------

class TestDarkLabWriteEndpointsRequireAuth:
    """All supply-chain write endpoints must reject anonymous (temp-session) requests with 401."""

    WRITE_ENDPOINTS = [
        ("PUT", DARKLAB_SUPPLY_CHAIN_TOOLS_URL, {"tool_overrides": {"send_email": {"description": "Pwned"}}}),
        ("POST", DARKLAB_SUPPLY_CHAIN_RESET_URL, None),
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

        assert resp.status_code in (401, 403), (
            f"{method} {url} should return 401 or 403 for anonymous session, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
    def test_auth_session_returns_200(self, client, auth_session, method, url, body):
        """Authenticated sessions should be allowed to modify tool overrides."""
        cookies = {
            settings.SESSION_COOKIE_NAME: auth_session.session_id,
            "csrf_token": auth_session.csrf_token,
        }
        headers = {settings.CSRF_HEADER_NAME: auth_session.csrf_token}
        
        # Pre-populate the server config so we don't get a 404
        client.get("/darklab/api/v1/supply-chain/servers/finmail", cookies=cookies, headers=headers)

        if method == "PUT":
            resp = client.put(url, json=body, cookies=cookies, headers=headers)
        elif method == "POST":
            resp = client.post(url, json=body, cookies=cookies, headers=headers)

        assert resp.status_code == 200, (
            f"{method} {url} should return 200 for authenticated session, got {resp.status_code}: {resp.text}"
        )

    def test_get_servers_allowed_for_anon(self, client):
        """GET (read-only) should still work for temp sessions — returns data, not 401."""
        _setup_temp_session(client)
        resp = client.get("/darklab/api/v1/supply-chain/servers")
        assert resp.status_code == 200
        assert "servers" in resp.json()
