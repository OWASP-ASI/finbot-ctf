"""Route-level auth tests for the Labs guardrail webhook config API.

GitHub issue #535: the guardrail write endpoints (PUT, POST /toggle,
POST /rotate-secret, DELETE, POST /test) used get_session_context, which
accepts anonymous temporary sessions. Since the /test endpoint fires an
immediate outbound HTTP request to whatever webhook_url is on file, an
anonymous visitor could both register an internal URL AND trigger a
request to it, with zero authentication -- unauthenticated SSRF.

This file was not part of the original fix in this PR; it closes a real
gap found by comparing against another contributor's independent fix
for the same issue (PR #538), which caught the missing-auth angle that
this PR's first pass missed (that pass only closed the DNS-resolution
bypass inside validate_webhook_url() itself). Verified against current
source before writing this: as of this commit, all 5 write endpoints
still used get_session_context.

Read endpoints (GET, GET /activity) intentionally stay anonymous-
readable -- no state-changing side effect, matches this codebase's own
convention (finbot/apps/ctf/routes/profile.py uses the same
authenticated-vs-anonymous split between its GET and PUT).

CSRF is deliberately bypassed in this file's own `client` fixture (the
default `fast_client`/CSRFProtectionMiddleware combination rejects
state-changing requests with a 403 before they ever reach route-level
auth, which isn't what these tests are checking). CSRF enforcement
itself already has its own coverage elsewhere; these tests exist to
verify the authentication guard added by this fix, in isolation.
"""

from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from finbot.core.auth.csrf import CSRFProtectionMiddleware
from finbot.core.auth.session import session_manager
from finbot.main import app

GUARDRAILS_PREFIX = "/labs/api/v1/guardrails"


async def _noop_csrf_dispatch(self, request: Request, call_next):
    return await call_next(request)


@pytest.fixture()
def client(db):
    with patch("finbot.main.start_processor_task", return_value=None):
        with patch.object(CSRFProtectionMiddleware, "dispatch", new=_noop_csrf_dispatch):
            with TestClient(app) as c:
                yield c


@pytest.fixture()
def temp_session(db):
    return session_manager.create_session()


@pytest.fixture()
def auth_session(db):
    return session_manager.create_session(email="guardrail_route_test@example.com")


@pytest.mark.unit
class TestGuardrailWriteEndpointsRequireAuth:

    def test_put_rejects_anonymous_session(self, client: TestClient, temp_session):
        response = client.put(
            GUARDRAILS_PREFIX,
            json={"webhook_url": "https://example.com/hook"},
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 401

    def test_toggle_rejects_anonymous_session(self, client: TestClient, temp_session):
        response = client.post(
            f"{GUARDRAILS_PREFIX}/toggle",
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 401

    def test_rotate_secret_rejects_anonymous_session(
        self, client: TestClient, temp_session
    ):
        response = client.post(
            f"{GUARDRAILS_PREFIX}/rotate-secret",
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 401

    def test_delete_rejects_anonymous_session(self, client: TestClient, temp_session):
        response = client.delete(
            GUARDRAILS_PREFIX,
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 401

    def test_test_webhook_rejects_anonymous_session(
        self, client: TestClient, temp_session
    ):
        response = client.post(
            f"{GUARDRAILS_PREFIX}/test",
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 401


@pytest.mark.unit
class TestGuardrailReadEndpointsStayAnonymous:
    """Regression: the read-only endpoints must NOT be affected by this
    fix -- they have no state-changing side effect and anonymous
    visitors are expected to be able to check config status."""

    def test_get_config_allows_anonymous_session(self, client: TestClient, temp_session):
        response = client.get(
            GUARDRAILS_PREFIX,
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 200

    def test_get_activity_allows_anonymous_session(
        self, client: TestClient, temp_session
    ):
        response = client.get(
            f"{GUARDRAILS_PREFIX}/activity",
            cookies={"finbot_session": temp_session.session_id},
        )
        assert response.status_code == 200


@pytest.mark.unit
class TestGuardrailWriteEndpointsAllowAuthenticatedSession:
    """Regression: legitimate, logged-in users must still be able to use
    every write endpoint -- this fix must not lock out real usage."""

    def test_put_allows_authenticated_session(self, client: TestClient, auth_session):
        response = client.put(
            GUARDRAILS_PREFIX,
            json={"webhook_url": "https://example.com/hook"},
            cookies={"finbot_session": auth_session.session_id},
        )
        assert response.status_code == 200

    def test_toggle_allows_authenticated_session(self, client: TestClient, auth_session):
        client.put(
            GUARDRAILS_PREFIX,
            json={"webhook_url": "https://example.com/hook"},
            cookies={"finbot_session": auth_session.session_id},
        )
        response = client.post(
            f"{GUARDRAILS_PREFIX}/toggle",
            cookies={"finbot_session": auth_session.session_id},
        )
        assert response.status_code == 200

    def test_delete_allows_authenticated_session(self, client: TestClient, auth_session):
        client.put(
            GUARDRAILS_PREFIX,
            json={"webhook_url": "https://example.com/hook"},
            cookies={"finbot_session": auth_session.session_id},
        )
        response = client.delete(
            GUARDRAILS_PREFIX,
            cookies={"finbot_session": auth_session.session_id},
        )
        assert response.status_code == 204
