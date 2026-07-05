"""Shared fixtures for security event unit tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from finbot.core.auth.session import SessionContext


@pytest.fixture
def session_context() -> SessionContext:
    """Minimal SessionContext for security emitter tests (no DB required)."""
    now = datetime.now(UTC)
    return SessionContext(
        session_id="sess_security_test",
        user_id="user_security_test",
        is_temporary=False,
        namespace="test_namespace",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        email="security-test@example.com",
        portal_type="vendor",
        current_vendor_id=42,
    )


@pytest.fixture
def mock_event_bus():
    """Patch event_bus.emit_agent_event for security module tests."""
    mock = AsyncMock()
    return mock
