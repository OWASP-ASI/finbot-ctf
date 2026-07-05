"""Tests for finbot.security.authorization."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finbot.core.auth.session import SessionContext
from finbot.security.authorization import (
    check_vendor_portal_scope,
    emit_authorization_decision,
    schedule_authorization_decision,
    schedule_vendor_portal_scope_check,
)
from finbot.security.schemas import SecurityEventCategory


def _vendor_session(vendor_id: int = 42) -> SessionContext:
    now = datetime.now(UTC)
    return SessionContext(
        session_id="sess_vendor",
        user_id="user_vendor",
        is_temporary=False,
        namespace="test_namespace",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        portal_type="vendor",
        current_vendor_id=vendor_id,
    )


def _admin_session() -> SessionContext:
    session = _vendor_session()
    return replace(session, portal_type="admin", current_vendor_id=None)


class TestEmitAuthorizationDecision:
    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_security_event", new_callable=AsyncMock)
    async def test_deny_payload_and_severity(self, mock_emit):
        session = _vendor_session(42)
        await emit_authorization_decision(
            session_context=session,
            action="view",
            allowed=False,
            reason="cross_vendor_access_denied",
            source="vendor_api.get_invoice",
            resource_type="invoice",
            resource_id=7,
            requested_vendor_id=99,
            workflow_id="wf_auth",
        )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.authorization_decision
        assert kwargs["severity"] == "warning"
        payload = kwargs["payload"]
        assert payload["allowed"] is False
        assert payload["resource_type"] == "invoice"
        assert payload["requested_vendor_id"] == 99
        assert payload["session_vendor_id"] == 42
        assert payload["portal_type"] == "vendor"

    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_security_event", new_callable=AsyncMock)
    async def test_allow_uses_info_severity(self, mock_emit):
        session = _admin_session()
        await emit_authorization_decision(
            session_context=session,
            action="view",
            allowed=True,
            reason="admin_portal_access",
            source="vendor_api.get_invoice",
        )

        assert mock_emit.call_args.kwargs["severity"] == "info"


class TestCheckVendorPortalScope:
    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_authorization_decision", new_callable=AsyncMock)
    async def test_same_vendor_allowed(self, mock_emit):
        session = _vendor_session(42)
        allowed = await check_vendor_portal_scope(
            session_context=session,
            owner_vendor_id=42,
            action="view",
            source="vendor_api.get_invoice",
            resource_type="invoice",
            resource_id=1,
        )

        assert allowed is True
        mock_emit.assert_awaited_once()
        assert mock_emit.call_args.kwargs["allowed"] is True
        assert mock_emit.call_args.kwargs["reason"] == "same_vendor"

    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_authorization_decision", new_callable=AsyncMock)
    async def test_cross_vendor_denied(self, mock_emit):
        session = _vendor_session(42)
        allowed = await check_vendor_portal_scope(
            session_context=session,
            owner_vendor_id=99,
            action="view",
            source="vendor_api.get_invoice",
            resource_type="invoice",
            resource_id=1,
        )

        assert allowed is False
        assert mock_emit.call_args.kwargs["allowed"] is False
        assert mock_emit.call_args.kwargs["reason"] == "cross_vendor_access_denied"

    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_authorization_decision", new_callable=AsyncMock)
    async def test_admin_portal_always_allowed(self, mock_emit):
        session = _admin_session()
        allowed = await check_vendor_portal_scope(
            session_context=session,
            owner_vendor_id=99,
            action="view",
            source="vendor_api.get_invoice",
            resource_type="invoice",
            resource_id=1,
        )

        assert allowed is True
        assert mock_emit.call_args.kwargs["reason"] == "admin_portal_access"

    @pytest.mark.asyncio
    @patch("finbot.security.authorization.emit_authorization_decision", new_callable=AsyncMock)
    async def test_admin_file_owner_none_denied_on_vendor_portal(self, mock_emit):
        session = _vendor_session(42)
        allowed = await check_vendor_portal_scope(
            session_context=session,
            owner_vendor_id=None,
            action="get_file",
            source="vendor_api.get_file",
            resource_type="file",
            resource_id=5,
        )

        assert allowed is False
        assert mock_emit.call_args.kwargs["requested_vendor_id"] is None


class TestScheduleAuthorizationDecision:
    @patch("finbot.security.authorization.emit_authorization_decision", new_callable=AsyncMock)
    def test_schedule_with_running_loop_creates_task(self, mock_emit):
        session = _vendor_session()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mock_loop = MagicMock()
            with patch("asyncio.get_running_loop", return_value=mock_loop):
                schedule_authorization_decision(
                    session_context=session,
                    action="list_inbox",
                    allowed=False,
                    reason="vendor_admin_inbox_denied",
                    source="finmail.list_inbox",
                )
            mock_loop.create_task.assert_called_once()
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    @patch("finbot.security.authorization.asyncio.run")
    def test_schedule_without_loop_uses_asyncio_run(self, mock_run):
        session = _vendor_session()
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            schedule_authorization_decision(
                session_context=session,
                action="get_file",
                allowed=False,
                reason="vendor_admin_file_denied",
                source="findrive.get_file",
            )
        mock_run.assert_called_once()


class TestScheduleVendorPortalScopeCheck:
    @patch("finbot.security.authorization.schedule_authorization_decision")
    def test_sync_scope_check_denied(self, mock_schedule):
        session = _vendor_session(42)
        allowed = schedule_vendor_portal_scope_check(
            session_context=session,
            owner_vendor_id=99,
            action="read_email",
            source="finmail.read_email",
            resource_type="message",
            resource_id=3,
        )

        assert allowed is False
        mock_schedule.assert_called_once()
        assert mock_schedule.call_args.kwargs["allowed"] is False
        assert mock_schedule.call_args.kwargs["reason"] == "cross_vendor_access_denied"

    @patch("finbot.security.authorization.schedule_authorization_decision")
    def test_sync_scope_check_admin_allowed(self, mock_schedule):
        session = _admin_session()
        allowed = schedule_vendor_portal_scope_check(
            session_context=session,
            owner_vendor_id=99,
            action="read_email",
            source="finmail.read_email",
            resource_type="message",
            resource_id=3,
        )

        assert allowed is True
        assert mock_schedule.call_args.kwargs["reason"] == "admin_portal_access"
