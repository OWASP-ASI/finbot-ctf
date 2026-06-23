"""Tests for guardrail webhook payload truncation fix and after_tool completeness.

Covers:
  GWT-TRN-001: Large payload is truncated at field level (body remains valid JSON)
  GWT-TRN-002: Normal-sized payload is sent unchanged (no truncation headers)
  GWT-TRN-003: X-Guardrail-Truncated and X-Guardrail-Full-Size headers are set on truncation
  GWT-TRN-004: HMAC signature is computed over valid (post-truncation) JSON body
  GWT-ATL-001: after_tool guardrail hook fires for complete_task before early return
"""

import hashlib
import hmac
import json
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from finbot.config import settings
from finbot.guardrails.schemas import HookKind, HookOutcome
from finbot.guardrails.service import GuardrailHookService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def session(db):
    """Create a session context for guardrail tests."""
    from finbot.core.auth.session import session_manager

    return session_manager.create_session(email="guardrail_trunc@example.com")


@pytest.fixture()
def config_repo(db, session):
    """Ensure a guardrail config with all hooks enabled exists."""
    from finbot.core.data.repositories import LabsGuardrailConfigRepository

    repo = LabsGuardrailConfigRepository(db, session)
    repo.upsert(
        webhook_url="https://example.com/hook",
        timeout_seconds=5,
        hooks={
            "before_tool": True,
            "after_tool": True,
            "before_model": True,
            "after_model": True,
        },
    )
    return repo


@pytest.fixture()
def service(session, config_repo):
    """GuardrailHookService wired to an active config."""
    return GuardrailHookService(session_context=session, workflow_id="wf_test_trunc")


# =============================================================================
# GWT-TRN: Payload Truncation
# =============================================================================


class TestPayloadTruncation:
    """Tests that verify the field-level truncation of large guardrail payloads."""

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_gwt_trn_001_large_payload_body_is_valid_json(
        self, mock_bus, service
    ):
        """GWT-TRN-001: Large payload truncated at field level — body is valid JSON.

        When the serialised envelope exceeds LABS_GUARDRAIL_MAX_PAYLOAD_BYTES,
        the service MUST cap string fields before serialisation so the webhook
        receiver always gets parseable JSON.
        """
        mock_bus.emit_agent_event = AsyncMock()

        original_limit = settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES
        settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = 500

        try:
            large_output = "X" * 1000  # forces truncation

            resp = httpx.Response(200, json={"verdict": "allow"})
            with patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
            ) as mock_post:
                outcome = await service.invoke(
                    HookKind.after_model,
                    model="gpt-4",
                    model_output=large_output,
                )

            assert outcome == HookOutcome.completed

            call_kwargs = mock_post.call_args.kwargs
            body: bytes = call_kwargs["content"]

            # Body MUST be parseable JSON
            try:
                parsed = json.loads(body.decode())
            except json.JSONDecodeError as exc:
                pytest.fail(f"Webhook body is not valid JSON after truncation: {exc}")

            # The model_output field must be present but shorter than the original
            assert "model_output" in parsed
            assert len(parsed["model_output"]) < len(large_output), (
                "model_output was not truncated"
            )

        finally:
            settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = original_limit

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_gwt_trn_002_normal_payload_not_truncated(self, mock_bus, service):
        """GWT-TRN-002: Normal-sized payload is sent unchanged without truncation headers."""
        mock_bus.emit_agent_event = AsyncMock()

        original_limit = settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES
        settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = 100_000  # very large limit

        try:
            small_output = "short response"

            resp = httpx.Response(200, json={"verdict": "allow"})
            with patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
            ) as mock_post:
                await service.invoke(
                    HookKind.after_model,
                    model="gpt-4",
                    model_output=small_output,
                )

            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]

            assert "X-Guardrail-Truncated" not in headers, (
                "Truncation header present for a payload that did not need truncation"
            )
            assert "X-Guardrail-Full-Size" not in headers

        finally:
            settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = original_limit

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_gwt_trn_003_truncation_headers_present_when_truncated(
        self, mock_bus, service
    ):
        """GWT-TRN-003: X-Guardrail-Truncated and X-Guardrail-Full-Size headers set on truncation."""
        mock_bus.emit_agent_event = AsyncMock()

        original_limit = settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES
        settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = 500

        try:
            resp = httpx.Response(200, json={"verdict": "allow"})
            with patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
            ) as mock_post:
                await service.invoke(
                    HookKind.after_model,
                    model="gpt-4",
                    model_output="Y" * 1000,
                )

            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            body: bytes = call_kwargs["content"]

            assert "X-Guardrail-Truncated" in headers, "Missing X-Guardrail-Truncated"
            assert headers["X-Guardrail-Truncated"] == "true"

            assert "X-Guardrail-Full-Size" in headers, "Missing X-Guardrail-Full-Size"
            full_size = int(headers["X-Guardrail-Full-Size"])
            assert full_size > len(body), (
                "X-Guardrail-Full-Size should be larger than the truncated body length"
            )

        finally:
            settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = original_limit

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_gwt_trn_004_hmac_computed_over_truncated_valid_json(
        self, mock_bus, service
    ):
        """GWT-TRN-004: HMAC signature is computed over the (valid-JSON) truncated body."""
        mock_bus.emit_agent_event = AsyncMock()

        original_limit = settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES
        settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = 500

        try:
            resp = httpx.Response(200, json={"verdict": "allow"})
            with patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
            ) as mock_post:
                await service.invoke(
                    HookKind.after_model,
                    model="gpt-4",
                    model_output="Z" * 1000,
                )

            call_kwargs = mock_post.call_args.kwargs
            body: bytes = call_kwargs["content"]
            headers = call_kwargs["headers"]

            timestamp = headers["X-Guardrail-Timestamp"]
            received_sig = headers["X-Guardrail-Signature"]

            # Load the signing secret directly from the config
            config = service._load_config()
            expected_msg = f"{timestamp}.".encode() + body
            expected_sig = hmac.new(
                config.signing_secret.encode(), expected_msg, hashlib.sha256
            ).hexdigest()

            assert received_sig == expected_sig, (
                "HMAC signature does not match signature over the truncated body"
            )

        finally:
            settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES = original_limit


# =============================================================================
# GWT-ATL: after_tool fired for complete_task
# =============================================================================


class TestAfterToolOnCompleteTask:
    """Tests that the after_tool guardrail hook is fired for complete_task."""

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_gwt_atl_001_after_tool_fires_for_complete_task(
        self, mock_bus, session
    ):
        """GWT-ATL-001: after_tool hook fires for complete_task before the agent loop exits.

        Before the fix, the agent returned immediately after complete_task
        succeeded, skipping the after_tool invocation entirely and leaving
        an unmatched before_tool event.
        """
        from finbot.agents.base import BaseAgent

        mock_bus.emit_agent_event = AsyncMock()
        mock_bus.set_workflow_context = MagicMock()
        mock_bus.clear_workflow_context = MagicMock()

        hook_calls: list[tuple[HookKind, str | None]] = []

        async def _mock_invoke(kind: HookKind, **kwargs):
            hook_calls.append((kind, kwargs.get("tool_name")))
            return HookOutcome.no_config

        # Build a minimal concrete agent
        class MinimalAgent(BaseAgent):
            def _load_config(self):
                return {}

            def _get_system_prompt(self):
                return "test"

            async def _get_user_prompt(self, task_data=None):
                return "do the task"

            def _get_tool_definitions(self):
                return []

            def _get_callables(self):
                return {}

            async def process(self, task_data, **kwargs):
                return await self._run_agent_loop(task_data)

        agent = MinimalAgent(session_context=session)
        # Patch the guardrail service on this instance
        agent._guardrail_service.invoke = _mock_invoke

        # Patch MCP server connection (no-op)
        agent._connect_mcp_servers = AsyncMock()
        agent._disconnect_mcp_servers = AsyncMock()

        # Simulate LLM returning a single complete_task tool call
        fake_tool_call = {
            "name": "complete_task",
            "call_id": "call_001",
            "arguments": {
                "task_status": "success",
                "task_summary": "All done",
            },
        }
        mock_response = MagicMock()
        mock_response.content = None
        mock_response.tool_calls = [fake_tool_call]
        mock_response.messages = []

        agent.llm_client = MagicMock()
        agent.llm_client.chat = AsyncMock(return_value=mock_response)

        # Run the agent loop
        result = await agent._run_agent_loop(task_data={})

        assert result["task_status"] == "success"

        # Both before_tool and after_tool must have been called for complete_task
        before_calls = [
            (k, t)
            for k, t in hook_calls
            if k == HookKind.before_tool and t == "complete_task"
        ]
        after_calls = [
            (k, t)
            for k, t in hook_calls
            if k == HookKind.after_tool and t == "complete_task"
        ]

        assert len(before_calls) >= 1, (
            "before_tool was not called for complete_task"
        )
        assert len(after_calls) >= 1, (
            "after_tool was never called for complete_task — hook is unpaired"
        )
        assert len(before_calls) == len(after_calls), (
            f"Unmatched before_tool/after_tool pairs: "
            f"{len(before_calls)} before vs {len(after_calls)} after"
        )
