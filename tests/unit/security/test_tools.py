"""Tests for finbot.security.tools."""

from unittest.mock import AsyncMock, patch

import pytest

from finbot.core.auth.session import SessionContext
from finbot.security.schemas import SecurityEventCategory
from finbot.security.tools import (
    OUTPUT_PREVIEW_MAX,
    emit_native_tool_output,
    emit_native_tool_parameters,
    emit_tool_output,
    emit_tool_parameters,
    emit_tool_selection,
)


class TestEmitToolSelection:
    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_valid_native_selection(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_tool_selection(
            session_context=session_context,
            tool_name="get_invoice",
            tool_source="native",
            source="invoice_agent.process",
            agent_name="invoice_agent",
            workflow_id="wf_1",
            iteration=2,
            call_id="call_abc",
            valid=True,
            available_tool_count=12,
        )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.tool_selection
        assert kwargs["severity"] == "info"
        assert kwargs["payload"]["tool_name"] == "get_invoice"
        assert kwargs["payload"]["valid"] is True
        assert kwargs["payload"]["iteration"] == 2
        assert kwargs["payload"]["call_id"] == "call_abc"

    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_invalid_selection_warning_severity(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_tool_selection(
            session_context=session_context,
            tool_name="bogus_tool",
            tool_source="unknown",
            source="invoice_agent.process",
            agent_name="invoice_agent",
            valid=False,
        )

        assert mock_emit.call_args.kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_mcp_server_parsed_from_namespaced_tool(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_tool_selection(
            session_context=session_context,
            tool_name="finmail__list_inbox",
            tool_source="mcp",
            source="invoice_agent.process",
            agent_name="invoice_agent",
        )

        assert mock_emit.call_args.kwargs["payload"]["mcp_server"] == "finmail"


class TestEmitToolParameters:
    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_mcp_parameters_payload(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_tool_parameters(
            session_context=session_context,
            agent_name="invoice_agent",
            tool_name="send_email",
            tool_source="mcp",
            arguments={"to": ["x@y.com"]},
            source="mcp.provider",
            mapped_from_event_type="mcp_tool_call_start",
            namespaced_tool_name="finmail__send_email",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert mock_emit.call_args.kwargs["category"] == SecurityEventCategory.tool_parameters
        assert payload["mapped_from_event_type"] == "mcp_tool_call_start"
        assert payload["mcp_server"] == "finmail"
        assert payload["namespaced_tool_name"] == "finmail__send_email"

    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_native_wrapper_merges_args(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_native_tool_parameters(
            session_context=session_context,
            agent_name="onboarding_agent",
            tool_name="update_vendor_status",
            tool_args=[1],
            tool_kwargs={"status": "approved"},
            workflow_id="wf_native",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["tool_source"] == "native"
        assert payload["source"] == "agent_tool"
        assert payload["arguments"]["status"] == "approved"
        assert payload["arguments"]["_positional_args"] == [1]


class TestEmitToolOutput:
    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_success_output_truncated(
        self, mock_emit, session_context: SessionContext
    ):
        long_output = "x" * (OUTPUT_PREVIEW_MAX + 500)
        await emit_tool_output(
            session_context=session_context,
            agent_name="invoice_agent",
            tool_name="get_file",
            tool_source="mcp",
            source="mcp.provider",
            mapped_from_event_type="mcp_tool_call_success",
            output=long_output,
            success=True,
            duration_ms=99.0,
            namespaced_tool_name="findrive__get_file",
        )

        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.tool_output
        assert kwargs["severity"] == "info"
        assert len(kwargs["payload"]["output"]) == OUTPUT_PREVIEW_MAX

    @pytest.mark.asyncio
    @patch("finbot.security.tools.emit_security_event", new_callable=AsyncMock)
    async def test_failure_includes_errors(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_native_tool_output(
            session_context=session_context,
            agent_name="invoice_agent",
            tool_name="get_invoice",
            success=False,
            duration_ms=5.0,
            error_type="ValueError",
            error_message="not found",
        )

        kwargs = mock_emit.call_args.kwargs
        assert kwargs["severity"] == "warning"
        assert kwargs["payload"]["success"] is False
        assert kwargs["payload"]["mapped_from_event_type"] == "tool_call_failure"
        assert kwargs["payload"]["error_type"] == "ValueError"
        assert "output" not in kwargs["payload"]
