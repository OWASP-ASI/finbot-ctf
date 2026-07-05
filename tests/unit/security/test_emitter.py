"""Tests for finbot.security.emitter."""

from unittest.mock import AsyncMock, patch

import pytest

from finbot.core.auth.session import SessionContext
from finbot.security.emitter import emit_security_event
from finbot.security.schemas import SecurityEventCategory


class TestEmitSecurityEvent:
    @pytest.mark.asyncio
    @patch("finbot.security.emitter.event_bus")
    async def test_emits_agent_event_with_security_subtype(
        self, mock_bus, session_context: SessionContext
    ):
        mock_bus.emit_agent_event = AsyncMock()

        await emit_security_event(
            category=SecurityEventCategory.memory_read,
            payload={"entity_type": "vendor", "entity_id": 1, "source": "test"},
            session_context=session_context,
            workflow_id="wf_test",
            summary="Security memory_read test",
        )

        mock_bus.emit_agent_event.assert_awaited_once()
        kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert kwargs["agent_name"] == "security"
        assert kwargs["event_type"] == "memory_read"
        assert kwargs["event_subtype"] == "security"
        assert kwargs["session_context"] is session_context
        assert kwargs["workflow_id"] == "wf_test"
        assert kwargs["summary"] == "Security memory_read test"

    @pytest.mark.asyncio
    @patch("finbot.security.emitter.event_bus")
    async def test_event_data_contains_validated_security_event(
        self, mock_bus, session_context: SessionContext
    ):
        mock_bus.emit_agent_event = AsyncMock()

        payload = {"tool_name": "update_vendor", "tool_source": "native", "valid": True}
        await emit_security_event(
            category=SecurityEventCategory.tool_selection,
            payload=payload,
            session_context=session_context,
            workflow_id="wf_sel",
            severity="info",
        )

        event_data = mock_bus.emit_agent_event.call_args.kwargs["event_data"]
        assert event_data["schema_version"] == "1"
        assert event_data["category"] == "tool_selection"
        assert event_data["session_id"] == session_context.session_id
        assert event_data["workflow_id"] == "wf_sel"
        assert event_data["payload"] == payload
        assert event_data["severity"] == "info"
        assert event_data["timestamp"].endswith("Z")

    @pytest.mark.asyncio
    @patch("finbot.security.emitter.event_bus")
    async def test_empty_workflow_id_when_not_provided(
        self, mock_bus, session_context: SessionContext
    ):
        mock_bus.emit_agent_event = AsyncMock()

        await emit_security_event(
            category=SecurityEventCategory.guardrail_trigger,
            payload={"hook_kind": "before_tool"},
            session_context=session_context,
        )

        event_data = mock_bus.emit_agent_event.call_args.kwargs["event_data"]
        assert event_data["workflow_id"] == ""
        assert mock_bus.emit_agent_event.call_args.kwargs["workflow_id"] is None

    @pytest.mark.asyncio
    @patch("finbot.security.emitter.event_bus")
    async def test_custom_agent_name(self, mock_bus, session_context: SessionContext):
        mock_bus.emit_agent_event = AsyncMock()

        await emit_security_event(
            category=SecurityEventCategory.authorization_decision,
            payload={"allowed": False, "reason": "cross_vendor_access_denied"},
            session_context=session_context,
            agent_name="custom_security_agent",
        )

        kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert kwargs["agent_name"] == "custom_security_agent"
        assert kwargs["event_data"]["agent_name"] == "custom_security_agent"

    @pytest.mark.asyncio
    @patch("finbot.security.emitter.event_bus")
    async def test_emit_failure_is_swallowed(
        self, mock_bus, session_context: SessionContext
    ):
        mock_bus.emit_agent_event = AsyncMock(side_effect=RuntimeError("redis down"))

        # Should not raise
        await emit_security_event(
            category=SecurityEventCategory.tool_output,
            payload={"tool_name": "test", "success": True},
            session_context=session_context,
        )

        mock_bus.emit_agent_event.assert_awaited_once()
