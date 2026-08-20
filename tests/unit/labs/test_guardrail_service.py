"""Tests for GuardrailHookService: HTTP calls, HMAC signing, verdict parsing, caching."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import LabsGuardrailConfigRepository
from finbot.guardrails.schemas import HookEnvelope, HookKind, HookOutcome
from finbot.guardrails.service import (
    GuardrailHookService,
    _truncate_envelope_for_payload_limit,
)


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
# Payload truncation (issue #525) -- must produce valid JSON, never a raw
# byte-slice of the serialized body.
# =============================================================================


def _make_envelope(**overrides) -> HookEnvelope:
    defaults = dict(
        hook_kind=HookKind.after_tool,
        session_id="sess_1",
        workflow_id="wf_1",
        tool_name="some_tool",
        tool_source="native",
        tool_arguments=None,
        tool_result=None,
        model=None,
        user_message=None,
        model_output=None,
        timestamp="2026-08-20T00:00:00Z",
    )
    defaults.update(overrides)
    return HookEnvelope(**defaults)


class TestPayloadTruncation:

    @pytest.mark.unit
    def test_returns_unchanged_when_already_under_limit(self):
        envelope = _make_envelope(tool_result="short")
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=65536)
        assert result.tool_result == "short"

    @pytest.mark.unit
    def test_truncated_body_is_always_valid_json(self):
        """The actual bug: a raw byte-slice of serialized JSON can cut a
        string or multi-byte UTF-8 character mid-way, producing invalid
        JSON. Field-level truncation must never do that. 300 bytes is
        near the floor -- above the envelope's fixed-field overhead but
        still forcing model_output to be truncated hard, including right
        through a run of multi-byte UTF-8 characters."""
        envelope = _make_envelope(
            model_output="hello ééé world " * 500  # multi-byte chars
        )
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=300)

        body = result.model_dump_json().encode()
        assert len(body) <= 300
        json.loads(body)  # must not raise

    @pytest.mark.unit
    def test_truncates_long_tool_result(self):
        envelope = _make_envelope(tool_result="x" * 5000)
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=500)
        assert len(result.model_dump_json().encode()) <= 500
        json.loads(result.model_dump_json())

    @pytest.mark.unit
    def test_truncates_long_user_message_and_model_output_together(self):
        envelope = _make_envelope(
            user_message="a" * 3000, model_output="b" * 3000
        )
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=1000)
        assert len(result.model_dump_json().encode()) <= 1000
        json.loads(result.model_dump_json())

    @pytest.mark.unit
    def test_large_tool_arguments_replaced_with_truncation_marker(self):
        """A dict can't be safely character-truncated without risking
        invalid JSON -- must become a small, valid marker instead, not a
        partially-cut object literal."""
        envelope = _make_envelope(tool_arguments={"data": "y" * 5000})
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=500)

        body = result.model_dump_json().encode()
        assert len(body) <= 500
        parsed = json.loads(body)
        assert parsed["tool_arguments"]["_truncated"] is True
        assert parsed["tool_arguments"]["keys"] == ["data"]
        assert parsed["tool_arguments"]["original_size_bytes"] > 500

    @pytest.mark.unit
    def test_does_not_over_truncate_when_only_slightly_over_limit(self):
        envelope = _make_envelope(tool_result="x" * 600)
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=590)
        # Should still contain most of the content, not be wiped to empty
        assert result.tool_result is not None
        assert len(result.tool_result) > 0

    @pytest.mark.unit
    def test_pathological_max_payload_below_fixed_overhead(self):
        """max_payload smaller than the envelope's own fixed-field
        overhead: even with every truncatable field emptied, the result
        can still exceed max_payload. Must not raise, and must still be
        valid JSON -- this is the documented, accepted limit of a
        best-effort truncation, not a crash."""
        envelope = _make_envelope(tool_result="x" * 5000)
        result = _truncate_envelope_for_payload_limit(envelope, max_payload=10)

        body = result.model_dump_json().encode()
        json.loads(body)  # must not raise
        assert result.tool_result == ""


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
    async def test_invoke_never_raises_even_on_internal_failure(self, mock_bus):
        """invoke()'s own docstring promises it never raises, so a bug or
        outage anywhere in its plumbing (not just the HTTP call, which
        already had its own try/except) can never propagate into a
        caller's unrelated try/except and get misclassified as that
        caller's own failure -- exactly the risk a reviewer flagged when
        the after_tool call for complete_task in base.py's agent loop
        landed inside the same try/except as the tool call itself."""
        mock_bus.emit_agent_event = AsyncMock()

        with patch(
            "finbot.guardrails.service.GuardrailHookService._sign_payload",
            side_effect=RuntimeError("boom"),
        ):
            svc = self._make_service()
            outcome = await svc.invoke(HookKind.before_tool, tool_name="test")

        assert outcome == HookOutcome.error

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
        assert "X-Guardrail-Truncated" not in call_kwargs["headers"]

    @pytest.mark.asyncio
    @patch("finbot.guardrails.service.event_bus")
    async def test_oversized_payload_sends_valid_json_and_truncated_header(
        self, mock_bus, monkeypatch
    ):
        """End-to-end proof for issue #525: a real oversized hook still
        produces a body the receiver can json.loads() without error, with
        a signature computed over that same valid body, plus an explicit
        header telling the receiver truncation happened."""
        mock_bus.emit_agent_event = AsyncMock()
        monkeypatch.setattr(
            "finbot.guardrails.service.settings.LABS_GUARDRAIL_MAX_PAYLOAD_BYTES", 300
        )

        resp = httpx.Response(200, json={"verdict": "allow"})
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp
        ) as mock_post:
            svc = self._make_service()
            await svc.invoke(
                HookKind.after_model,
                model="gpt-5-nano",
                model_output="x" * 5000,
            )

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["X-Guardrail-Truncated"] == "true"
        sent_body = call_kwargs["content"]
        json.loads(sent_body)  # must not raise -- the actual bug being fixed

        # Signature must be computed over the exact body that was sent.
        expected_sig = GuardrailHookService._sign_payload(
            sent_body,
            svc._config.signing_secret,
            call_kwargs["headers"]["X-Guardrail-Timestamp"],
        )
        assert call_kwargs["headers"]["X-Guardrail-Signature"] == expected_sig

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
