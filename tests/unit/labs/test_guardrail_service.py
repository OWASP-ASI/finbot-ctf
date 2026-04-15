"""Tests for GuardrailHookService: HTTP calls, HMAC signing, verdict parsing, caching."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import LabsGuardrailConfigRepository
from finbot.guardrails.schemas import HookKind, HookOutcome
from finbot.guardrails.service import GuardrailHookService


@pytest.fixture()
def session(db):
    """Create a session and return context."""
    return session_manager.create_session(email="guardrail_svc@example.com")


@pytest.fixture()
def config_repo(db, session):
    """Repo with a config already saved."""
    repo = LabsGuardrailConfigRepository(db, session)
    repo.upsert(
        webhook_url="https://example.com/hook",
        timeout_seconds=5,
    )
    return repo


@pytest.fixture()
def service(session):
    return GuardrailHookService(session_context=session, workflow_id="wf_test_123")


# =============================================================================
# Config loading + caching
# =============================================================================


class TestConfigCaching:
    def test_no_config_returns_no_config_outcome(self, service):
        import asyncio
        outcome = asyncio.get_event_loop().run_until_complete(
            service.invoke(HookKind.before_tool, tool_name="test_tool")
        )
        assert outcome == HookOutcome.no_config

    def test_disabled_hook_returns_hook_disabled(self, db, session, config_repo):
        config_repo.upsert(
            webhook_url="https://example.com/hook",
            hooks={"before_tool": False, "after_tool": True,
                   "before_model": True, "after_model": True},
        )
        svc = GuardrailHookService(session_context=session, workflow_id="wf_test")

        import asyncio
        outcome = asyncio.get_event_loop().run_until_complete(
            svc.invoke(HookKind.before_tool, tool_name="test_tool")
        )
        assert outcome == HookOutcome.hook_disabled

    def test_config_loaded_once(self, db, session, config_repo):
        """Config DB query happens only once (cached)."""
        svc = GuardrailHookService(session_context=session, workflow_id="wf_test")

        with patch.object(
            LabsGuardrailConfigRepository, "get_for_current_user"
        ) as mock_get:
            mock_get.return_value = None
            svc._load_config()
            svc._load_config()
            assert mock_get.call_count == 1


# =============================================================================
# HMAC signing
# =============================================================================


class TestHMACSigning:
    def test_sign_payload_deterministic(self):
        body = b'{"hook_kind":"before_tool"}'
        secret = "test_secret_key"
        ts = "2026-04-09T00:00:00Z"

        sig1 = GuardrailHookService._sign_payload(body, secret, ts)
        sig2 = GuardrailHookService._sign_payload(body, secret, ts)
        assert sig1 == sig2

    def test_sign_payload_matches_manual_hmac(self):
        body = b'{"test":"data"}'
        secret = "my_secret"
        ts = "2026-04-09T12:00:00Z"

        expected_msg = f"{ts}.".encode() + body
        expected = hmac.new(secret.encode(), expected_msg, hashlib.sha256).hexdigest()

        actual = GuardrailHookService._sign_payload(body, secret, ts)
        assert actual == expected

    def test_different_secret_different_signature(self):
        body = b'{"test":"data"}'
        ts = "2026-04-09T00:00:00Z"

        sig1 = GuardrailHookService._sign_payload(body, "secret_a", ts)
        sig2 = GuardrailHookService._sign_payload(body, "secret_b", ts)
        assert sig1 != sig2


# =============================================================================
# Webhook invocation (mocked HTTP)
# =============================================================================


class TestWebhookInvocation:
    @pytest.fixture(autouse=True)
    def _setup(self, db, session, config_repo):
        self.session = session
        self.db = db

    def _make_service(self):
        return GuardrailHookService(
            session_context=self.session, workflow_id="wf_test"
        )

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_allow_verdict(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, json={"verdict": "allow", "reason": "looks safe"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            outcome = await svc.invoke(
                HookKind.before_tool, tool_name="approve_invoice", tool_source="native"
            )

        assert outcome == HookOutcome.completed
        mock_bus.emit_agent_event.assert_called_once()
        call_kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert call_kwargs["agent_name"] == "guardrail"
        assert call_kwargs["event_type"] == "webhook_completed"
        assert call_kwargs["event_data"]["verdict"] == "allow"
        assert call_kwargs["event_data"]["hook_kind"] == "before_tool"

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_block_verdict(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, json={"verdict": "block", "reason": "suspicious"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            outcome = await svc.invoke(
                HookKind.before_tool, tool_name="approve_invoice"
            )

        assert outcome == HookOutcome.completed
        call_kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert call_kwargs["event_data"]["verdict"] == "block"

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_timeout(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.before_tool, tool_name="test")

        assert outcome == HookOutcome.timeout
        call_kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert call_kwargs["event_type"] == "webhook_timeout"

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_http_error(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(500, text="Internal Server Error")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.after_tool, tool_name="test")

        assert outcome == HookOutcome.error
        call_kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert call_kwargs["event_type"] == "webhook_error"
        assert call_kwargs["event_data"]["http_status"] == 500

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_invalid_verdict_body(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, json={"verdict": "maybe"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.before_tool, tool_name="test")

        assert outcome == HookOutcome.invalid_verdict

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_invalid_json_response(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, text="not json at all")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.before_tool, tool_name="test")

        assert outcome == HookOutcome.invalid_verdict

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_connection_error(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.before_tool, tool_name="test")

        assert outcome == HookOutcome.error

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_signature_header_sent(self, mock_bus):
        """Verify the webhook POST includes the HMAC signature header."""
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, json={"verdict": "allow"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp) as mock_post:
            svc = self._make_service()
            await svc.invoke(HookKind.before_tool, tool_name="test")

        call_kwargs = mock_post.call_args.kwargs
        assert "X-Guardrail-Signature" in call_kwargs["headers"]
        assert "X-Guardrail-Timestamp" in call_kwargs["headers"]
        assert len(call_kwargs["headers"]["X-Guardrail-Signature"]) == 64  # SHA256 hex

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_event_includes_latency(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        resp = httpx.Response(200, json={"verdict": "allow"})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            svc = self._make_service()
            await svc.invoke(HookKind.before_tool, tool_name="test")

        call_kwargs = mock_bus.emit_agent_event.call_args.kwargs
        assert "latency_ms" in call_kwargs["event_data"]
        assert isinstance(call_kwargs["event_data"]["latency_ms"], int)
