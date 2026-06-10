"""Tests for SESSION_COOKIE_SECURE enforcement.

Covers:
- Issue #202: Session cookies sent over HTTP by default
"""

import pytest

from finbot.config import Settings


def test_production_rejects_insecure_cookies():
    """Production mode (DEBUG=False) must reject SESSION_COOKIE_SECURE=False."""
    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE must be True"):
        Settings(
            DEBUG=False,
            SESSION_COOKIE_SECURE=False,
            SECRET_KEY="a-real-production-secret-key-that-is-not-default",
        )


def test_production_accepts_secure_cookies():
    """Production mode (DEBUG=False) with SESSION_COOKIE_SECURE=True should work."""
    s = Settings(
        DEBUG=False,
        SESSION_COOKIE_SECURE=True,
        SECRET_KEY="a-real-production-secret-key-that-is-not-default",
    )
    assert s.SESSION_COOKIE_SECURE is True


def test_dev_mode_allows_insecure_cookies():
    """Development mode (DEBUG=True) can use insecure cookies for local testing."""
    s = Settings(
        DEBUG=True,
        SESSION_COOKIE_SECURE=False,
    )
    assert s.SESSION_COOKIE_SECURE is False


def test_dev_mode_allows_secure_cookies():
    """Development mode (DEBUG=True) with secure cookies should also work."""
    s = Settings(
        DEBUG=True,
        SESSION_COOKIE_SECURE=True,
    )
    assert s.SESSION_COOKIE_SECURE is True
