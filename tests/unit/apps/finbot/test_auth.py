"""
Magic Link Authentication Tests
 
User Story:
As a user,
I want to sign in via a magic link sent to my email
So that I can access the platform without a password
 
Acceptance Criteria:
- Authenticated users are redirected to /portals on all auth pages ✓
- Requesting a magic link persists a token and sends an email ✓
- A DB failure on token creation returns an error page, not a 5xx ✓
- An invalid or already-used token shows an error page ✓
- An expired token shows an error page ✓
- A valid token marks itself used and upgrades the session ✓
- If session upgrade fails, a new session is created ✓
- If session creation fails, an error page is shown ✓
- Logout deletes the current session and issues a new temporary one ✓
 
Testing Notes:
- Use ``follow_redirects=False`` when asserting a 303 status code.
- Set cookies on the client instance, not per-request (Starlette deprecation
  silently drops per-request cookies).
- ``session_manager`` is a singleton — use ``side_effect=[val1, val2]`` when
  middleware and route both call the same method in one request.
- Middleware post-processing overwrites the response cookie if
  ``session_context.needs_cookie_update`` is True. Tests asserting the route's
  cookie must patch ``get_session`` and set ``needs_cookie_update = False``.
"""
import uuid
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from finbot.config import settings
from finbot.core.data.models import MagicLinkToken
from finbot.core.data.database import SessionLocal
from finbot.core.auth.session import SessionContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_dt(minutes: int = 30) -> datetime:
    """Return a timezone-aware datetime in the future."""
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _uid() -> str:
    """Short unique string for token / session IDs."""
    return uuid.uuid4().hex[:12]


def _make_session_context(
    session_id: str | None = None,
    is_temporary: bool = False,
    email: str = "test@example.com",
) -> SessionContext:
    """Create a minimal real SessionContext so middleware doesn't choke on it."""
    now = datetime.now(UTC)
    return SessionContext(
        session_id=session_id or _uid(),
        user_id=_uid(),
        is_temporary=is_temporary,
        namespace="test-ns",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        email=None if is_temporary else email,
    )


def _insert_magic_token(
    token: str,
    email: str,
    session_id: str | None = None,
    expires_at: datetime | None = None,
) -> MagicLinkToken:
    """Insert a MagicLinkToken into the test DB and return it."""
    db = SessionLocal()
    try:
        magic_token = MagicLinkToken(
            token=token,
            email=email,
            session_id=session_id,
            expires_at=expires_at or _future_dt(),
            ip_address=None,
        )
        db.add(magic_token)
        db.commit()
        return magic_token
    finally:
        db.close()


def _authenticated_middleware_patches(authed_ctx: SessionContext):
    """
    Return a stack of patches that makes the SessionMiddleware inject an
    authenticated session into ``request.state.session_context``.

    The test client has a fake cookie set so the middleware takes the
    ``get_session`` branch.  ``load_vendor_context`` is stubbed to a no-op
    so no real DB queries happen for vendor data.
    """
    return [
        patch(
            "finbot.core.auth.middleware.session_manager.get_session",
            return_value=(authed_ctx, "session_active"),
        ),
        patch(
            "finbot.core.auth.middleware.session_manager.load_vendor_context",
            side_effect=lambda ctx: ctx,
        ),
    ]


FAKE_SESSION_COOKIE_VALUE = "fake-authed-session-id"

# ---------------------------------------------------------------------------
# POST /auth/magic-link
# ---------------------------------------------------------------------------

@pytest.mark.web
def test_request_magic_link_redirects_if_authenticated(client):
    """CD001-WEB-001: Already-authenticated users are sent straight to /portals."""
    authed = _make_session_context(is_temporary=False)
    patches = _authenticated_middleware_patches(authed)
    # Set cookie on the client instance (per-request cookies are deprecated).
    client.cookies.set(settings.SESSION_COOKIE_NAME, FAKE_SESSION_COOKIE_VALUE)
    try:
        with patches[0], patches[1]:
            response = client.post(
                "/auth/magic-link",
                data={"email": "user@example.com"},
                follow_redirects=False,
            )
    finally:
        client.cookies.clear()
    assert response.status_code == 303
    assert response.headers["location"] == "/portals"


@pytest.mark.web
def test_request_magic_link_creates_token_and_sends_email(client):
    """CD001-WEB-002: A token is persisted and the email service is called with a verify URL."""
    email = f"ml-create-{_uid()}@example.com"
    mock_send = AsyncMock()

    with patch("finbot.apps.finbot.auth.get_email_service") as mock_svc, \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        mock_svc.return_value.send_magic_link = mock_send
        response = client.post(
            "/auth/magic-link",
            data={"email": email},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "/auth/check-email" in response.headers["location"]

    db = SessionLocal()
    try:
        token_obj = db.query(MagicLinkToken).filter(MagicLinkToken.email == email).first()
        assert token_obj is not None
        assert token_obj.token is not None
    finally:
        db.close()

    mock_send.assert_called_once()
    call_email, call_link = mock_send.call_args.args
    assert call_email == email
    assert "/auth/verify?token=" in call_link


@pytest.mark.web
def test_request_magic_link_db_exception_returns_error_page(client):
    """CD001-WEB-003: A DB failure returns an error page (no 5xx crash)."""
    mock_db_instance = MagicMock()
    mock_db_instance.commit.side_effect = Exception("DB error")

    with patch("finbot.apps.finbot.auth.get_email_service"), \
         patch("finbot.apps.finbot.auth.SessionLocal", return_value=mock_db_instance), \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.post("/auth/magic-link", data={"email": "fail@example.com"})

    assert response.status_code == 200
    assert "Failed to send magic link" in response.text


# ---------------------------------------------------------------------------
# GET /auth/verify
# ---------------------------------------------------------------------------

@pytest.mark.web
def test_verify_magic_link_invalid_token_returns_error(client):
    """CD001-WEB-004: A token that doesn't exist in the DB shows the 'Invalid link' page."""
    with patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get(f"/auth/verify?token=does-not-exist-{_uid()}")

    assert response.status_code == 200
    assert "Invalid link" in response.text


@pytest.mark.web
def test_verify_magic_link_expired_token_returns_error(client):
    """CD001-WEB-005: An expired token shows the 'Link expired' error page."""
    token = f"expired-{_uid()}"
    _insert_magic_token(token, f"expired-{_uid()}@example.com")

    with patch.object(MagicLinkToken, "is_valid", return_value=False), \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get(f"/auth/verify?token={token}")

    assert response.status_code == 200
    assert "Link expired" in response.text


@pytest.mark.web
def test_verify_magic_link_marks_token_used_and_upgrades_session(client):
    """CD001-WEB-006: On a valid token, used_at is set and upgrade_to_permanent is called."""
    token = f"valid-{_uid()}"
    session_id = _uid()
    _insert_magic_token(token, f"valid-{_uid()}@example.com", session_id=session_id)

    perm_session = _make_session_context(is_temporary=False)

    # Give the middleware a pre-existing temp session so it doesn't call
    # create_session and won't overwrite the cookie the route sets on the response.
    # needs_cookie_update=False tells the middleware post-processing to leave the
    # response cookies alone.
    middleware_ctx = _make_session_context(is_temporary=True)
    middleware_ctx.needs_cookie_update = False

    client.cookies.set(settings.SESSION_COOKIE_NAME, "existing-temp-session")
    try:
        with patch.object(MagicLinkToken, "is_valid", return_value=True), \
             patch("finbot.apps.finbot.auth.session_manager.upgrade_to_permanent",
                   return_value=(perm_session, None)) as mock_upgrade, \
             patch("finbot.core.auth.middleware.session_manager.get_session",
                   return_value=(middleware_ctx, "session_active")), \
             patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
                   side_effect=lambda ctx: ctx):
            response = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    finally:
        client.cookies.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"
    assert response.cookies.get("finbot_session") == perm_session.session_id
    mock_upgrade.assert_called_once()

    db = SessionLocal()
    try:
        used = db.query(MagicLinkToken).filter(MagicLinkToken.token == token).first()
        assert used.used_at is not None
    finally:
        db.close()


@pytest.mark.web
def test_verify_magic_link_upgrade_fails_creates_new_session(client):
    """CD001-WEB-007: If upgrade_to_permanent returns (None, None), a new session is created."""
    token = f"fallback-{_uid()}"
    _insert_magic_token(token, f"fallback-{_uid()}@example.com", session_id=_uid())

    new_session = _make_session_context(is_temporary=False)

    with patch.object(MagicLinkToken, "is_valid", return_value=True), \
         patch("finbot.apps.finbot.auth.session_manager.upgrade_to_permanent",
               return_value=(None, None)), \
         patch("finbot.apps.finbot.auth.session_manager.create_session",
               return_value=new_session), \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get(f"/auth/verify?token={token}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"
    assert response.cookies.get("finbot_session") == new_session.session_id


@pytest.mark.web
def test_verify_magic_link_session_creation_failure_returns_error(client):
    """CD001-WEB-008: If both upgrade and create_session return None, an error page is shown."""
    token = f"failsess-{_uid()}"
    _insert_magic_token(token, f"failsess-{_uid()}@example.com", session_id=_uid())

    # session_manager is a singleton — finbot.apps.web.auth.session_manager and
    # finbot.core.auth.middleware.session_manager are the *same object*, so two
    # separate patches for create_session would just have the last one win.
    #
    # Instead use a single patch with side_effect as an ordered list.
    # The middleware always runs first (no cookie → calls create_session to build
    # a temporary session for the visitor), then the route calls create_session
    # after upgrade_to_permanent fails.  So call order is:
    #   1st call → middleware needs a valid temp session to avoid AttributeError
    #   2nd call → route; return None to trigger the error page
    middleware_temp_session = _make_session_context(is_temporary=True)

    with patch.object(MagicLinkToken, "is_valid", return_value=True), \
         patch("finbot.apps.finbot.auth.session_manager.upgrade_to_permanent",
               return_value=(None, None)), \
         patch("finbot.apps.finbot.auth.session_manager.create_session",
               side_effect=[middleware_temp_session, None]), \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get(f"/auth/verify?token={token}")

    assert response.status_code == 200
    assert "Failed to create session" in response.text


@pytest.mark.web
def test_verify_magic_link_redirects_if_already_authenticated(client):
    """CD001-WEB-009: Visiting /auth/verify while already logged in redirects to /portals."""
    authed = _make_session_context(is_temporary=False)
    patches = _authenticated_middleware_patches(authed)
    # Set cookie on the client instance (per-request cookies are deprecated).
    client.cookies.set(settings.SESSION_COOKIE_NAME, FAKE_SESSION_COOKIE_VALUE)
    try:
        with patches[0], patches[1]:
            response = client.get(
                "/auth/verify?token=anything",
                follow_redirects=False,
            )
    finally:
        client.cookies.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"


# ---------------------------------------------------------------------------
# GET /auth/logout
# ---------------------------------------------------------------------------

@pytest.mark.web
def test_logout_deletes_session_and_creates_temp(client):
    """CD001-WEB-010: Logout deletes the old session, creates a temporary one, and sets cookie."""
    temp_session = _make_session_context(is_temporary=True)

    with patch("finbot.apps.finbot.auth.session_manager.delete_session") as mock_delete, \
         patch("finbot.apps.finbot.auth.session_manager.create_session",
               return_value=temp_session), \
         patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get("/auth/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"
    assert response.cookies.get("finbot_session") == temp_session.session_id
    mock_delete.assert_called_once()


# ---------------------------------------------------------------------------
# GET /auth/check-email
# ---------------------------------------------------------------------------

@pytest.mark.web
def test_check_email_renders_page(client):
    """CD001-WEB-011: The check-email page renders and includes the submitted email address."""
    with patch("finbot.core.auth.middleware.session_manager.load_vendor_context",
               side_effect=lambda ctx: ctx):
        response = client.get("/auth/check-email?email=check@example.com")

    assert response.status_code == 200
    assert "check@example.com" in response.text


@pytest.mark.web
def test_check_email_redirects_if_authenticated(client):
    """CD001-WEB-012: Already-authenticated users are redirected away from check-email."""
    authed = _make_session_context(is_temporary=False)
    patches = _authenticated_middleware_patches(authed)
    # Set cookie on the client instance (per-request cookies are deprecated).
    client.cookies.set(settings.SESSION_COOKIE_NAME, FAKE_SESSION_COOKIE_VALUE)
    try:
        with patches[0], patches[1]:
            response = client.get(
                "/auth/check-email?email=check@example.com",
                follow_redirects=False,
            )
    finally:
        client.cookies.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/portals"