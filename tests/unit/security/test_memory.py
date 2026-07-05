"""Tests for finbot.security.memory."""

from unittest.mock import AsyncMock, patch

import pytest

from finbot.core.auth.session import SessionContext
from finbot.security.memory import (
    CONTENT_PREVIEW_MAX,
    MEMORY_KEY_AGENT_NOTES,
    emit_agent_notes_read,
    emit_memory_read,
    emit_memory_write,
)
from finbot.security.schemas import SecurityEventCategory


class TestEmitMemoryRead:
    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_skips_empty_content(self, mock_emit, session_context: SessionContext):
        await emit_memory_read(
            session_context=session_context,
            entity_type="vendor",
            entity_id=1,
            content="   ",
            source="onboarding.get_vendor_details",
        )
        mock_emit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_emits_full_snapshot_payload(
        self, mock_emit, session_context: SessionContext
    ):
        notes = "Prior review: vendor looks legitimate."
        await emit_memory_read(
            session_context=session_context,
            entity_type="vendor",
            entity_id=7,
            content=notes,
            source="invoice_agent.get_vendor_details",
            consumer_agent="invoice_agent",
            workflow_id="wf_mem",
        )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.memory_read
        assert kwargs["severity"] == "info"
        payload = kwargs["payload"]
        assert payload["memory_key"] == MEMORY_KEY_AGENT_NOTES
        assert payload["entity_type"] == "vendor"
        assert payload["entity_id"] == 7
        assert payload["content_length"] == len(notes)
        assert payload["content_preview"] == notes
        assert payload["source"] == "invoice_agent.get_vendor_details"
        assert payload["consumer_agent"] == "invoice_agent"
        assert kwargs["workflow_id"] == "wf_mem"

    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_preview_truncated_at_max(
        self, mock_emit, session_context: SessionContext
    ):
        long_content = "a" * (CONTENT_PREVIEW_MAX + 50)
        await emit_memory_read(
            session_context=session_context,
            entity_type="invoice",
            entity_id=2,
            content=long_content,
            source="fraud.get_invoice_details",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["content_length"] == len(long_content)
        assert len(payload["content_preview"]) == CONTENT_PREVIEW_MAX


class TestEmitAgentNotesRead:
    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_memory_read", new_callable=AsyncMock)
    async def test_none_notes_skips_emit(self, mock_read, session_context: SessionContext):
        await emit_agent_notes_read(
            session_context=session_context,
            entity_type="vendor",
            entity_id=1,
            agent_notes=None,
            source="onboarding._get_user_prompt",
        )
        mock_read.assert_awaited_once()
        assert mock_read.call_args.kwargs["content"] == ""

    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_forwards_to_memory_read(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_agent_notes_read(
            session_context=session_context,
            entity_type="vendor",
            entity_id=3,
            agent_notes="  trusted vendor  ",
            source="payments.get_invoice_for_payment",
            consumer_agent="payments_agent",
        )

        mock_emit.assert_awaited_once()
        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["content_preview"] == "trusted vendor"
        assert payload["consumer_agent"] == "payments_agent"


class TestEmitMemoryWrite:
    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_delta_append_payload(
        self, mock_emit, session_context: SessionContext
    ):
        delta = "Flagged for manual review."
        await emit_memory_write(
            session_context=session_context,
            entity_type="invoice",
            entity_id=12,
            content=delta,
            source="invoice.update_invoice_agent_notes",
            write_mode="append",
            workflow_id="wf_write",
        )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == SecurityEventCategory.memory_write
        payload = kwargs["payload"]
        assert payload["memory_key"] == MEMORY_KEY_AGENT_NOTES
        assert payload["entity_type"] == "invoice"
        assert payload["entity_id"] == 12
        assert payload["write_mode"] == "append"
        assert payload["content_length"] == len(delta)
        assert payload["content_preview"] == delta
        assert payload["source"] == "invoice.update_invoice_agent_notes"

    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_empty_write_still_emits(
        self, mock_emit, session_context: SessionContext
    ):
        await emit_memory_write(
            session_context=session_context,
            entity_type="vendor",
            entity_id=1,
            content="",
            source="vendor.update_vendor_agent_notes",
        )

        mock_emit.assert_awaited_once()
        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["content_length"] == 0
        assert payload["content_preview"] == ""

    @pytest.mark.asyncio
    @patch("finbot.security.memory.emit_security_event", new_callable=AsyncMock)
    async def test_write_preview_truncated(
        self, mock_emit, session_context: SessionContext
    ):
        long_delta = "z" * (CONTENT_PREVIEW_MAX + 10)
        await emit_memory_write(
            session_context=session_context,
            entity_type="fraud",
            entity_id=5,
            content=long_delta,
            source="fraud.update_fraud_agent_notes",
        )

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["content_length"] == len(long_delta)
        assert len(payload["content_preview"]) == CONTENT_PREVIEW_MAX
