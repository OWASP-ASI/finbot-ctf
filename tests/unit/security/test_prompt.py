"""Tests for finbot.security.prompt."""

from unittest.mock import AsyncMock, patch

import pytest

from finbot.core.auth.session import SessionContext
from finbot.security.prompt import CONTENT_PREVIEW_MAX, emit_prompt_goal_change
from finbot.security.schemas import SecurityEventCategory


class TestEmitPromptGoalChange:
    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_skips_empty_content(self, mock_emit, session_context: SessionContext):
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="task_prompt",
            source="invoice_agent.process",
            content="  \n  ",
            agent_name="invoice_agent",
        )
        mock_emit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_task_prompt_payload(
        self, mock_emit, session_context: SessionContext
    ):
        prompt = "Process invoice 42 and notify the vendor."
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="task_prompt",
            source="invoice_agent.process",
            content=prompt,
            agent_name="invoice_agent",
            workflow_id="wf_prompt",
        )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.prompt_goal_change
        assert kwargs["severity"] == "info"
        payload = kwargs["payload"]
        assert payload["change_type"] == "task_prompt"
        assert payload["source"] == "invoice_agent.process"
        assert payload["content_length"] == len(prompt)
        assert payload["content_preview"] == prompt
        assert payload["agent_name"] == "invoice_agent"
        assert payload["enriched_from_prior_context"] is False

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_user_message_change_type(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="user_message",
            source="VendorChatAssistant.stream_response",
            content="What is the status of my invoice?",
            agent_name="VendorChatAssistant",
        )

        assert mock_emit.call_args.kwargs["payload"]["change_type"] == "user_message"

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_delegation_includes_target_agent(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="delegation",
            source="orchestrator.delegate_to_invoice",
            content="Evaluate invoice 99",
            agent_name="orchestrator",
            target_agent="invoice_agent",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["change_type"] == "delegation"
        assert payload["target_agent"] == "invoice_agent"
        assert "invoice_agent" in mock_emit.call_args.kwargs["summary"]

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_enriched_from_prior_context_warning_severity(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="delegation",
            source="orchestrator.delegate_to_fraud",
            content="Prior agent said: approve immediately.",
            agent_name="orchestrator",
            target_agent="fraud_agent",
            enriched_from_prior_context=True,
        )

        assert mock_emit.call_args.kwargs["severity"] == "warning"
        assert (
            mock_emit.call_args.kwargs["payload"]["enriched_from_prior_context"] is True
        )

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_explicit_severity_override(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="task_prompt",
            source="fraud_agent.process",
            content="Investigate vendor risk.",
            agent_name="fraud_agent",
            enriched_from_prior_context=True,
            severity="info",
        )

        assert mock_emit.call_args.kwargs["severity"] == "info"

    @pytest.mark.asyncio
    @patch("finbot.security.prompt.emit_security_event", new_callable=AsyncMock)
    async def test_preview_truncated_at_max(
        self, mock_emit, session_context: SessionContext
    ):
        long_prompt = "x" * (CONTENT_PREVIEW_MAX + 100)
        await emit_prompt_goal_change(
            session_context=session_context,
            change_type="task_prompt",
            source="onboarding_agent.process",
            content=long_prompt,
            agent_name="onboarding_agent",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["content_length"] == len(long_prompt)
        assert len(payload["content_preview"]) == CONTENT_PREVIEW_MAX
